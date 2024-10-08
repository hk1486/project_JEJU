from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, APIRouter
from fastapi.responses import JSONResponse
import os
from sshtunnel import SSHTunnelForwarder
import pymysql
import pandas as pd
import requests
from copy import deepcopy
import json
import ast
import warnings
warnings.filterwarnings('ignore')

load_dotenv()

router = APIRouter()

MYSQL_HOSTNAME = os.getenv('MYSQL_HOSTNAME')
MYSQL_PORT = int(os.getenv('MYSQL_PORT'))
MYSQL_USERNAME = os.getenv('MYSQL_USERNAME')
MYSQL_PASSWORD = os.getenv('MYSQL_PASSWORD')
MYSQL_DATABASE = os.getenv('MYSQL_DATABASE')

def connect_mysql(query):
    try:
        connection = pymysql.connect(
            host=MYSQL_HOSTNAME,
            port=MYSQL_PORT,
            user=MYSQL_USERNAME,
            password=MYSQL_PASSWORD,
            database=MYSQL_DATABASE
        )
        # 쿼리를 실행하여 데이터를 가져오기
        df = pd.read_sql(query, connection)
        return df

    except Exception as e:
        print(f"Error: {str(e)}")
        return pd.DataFrame()  # 오류 발생 시 빈 DataFrame 반환

    finally:
        connection.close()


# 문자열을 리스트로 변환하는 함수
def convert_string_to_list(tag_string):
    # ast.literal_eval로 문자열을 리스트로 변환
    if not tag_string:
        return []
    if isinstance(tag_string, list):
        return tag_string
    if isinstance(tag_string, str):
        tag_string = tag_string.strip()
        # Try to parse with json.loads
        try:
            return json.loads(tag_string)
        except json.JSONDecodeError:
            pass
        # Try to parse with ast.literal_eval
        try:
            return ast.literal_eval(tag_string)
        except (ValueError, SyntaxError):
            pass
        # If all else fails, assume it's a comma-separated string
        return [tag.strip() for tag in tag_string.split(',')]
    return []


# 추천 함수
def recommend_tourist_spots(user_tags, df):
    df = df[df['tag'].notnull()]

    df['tag'] = df['tag'].apply(convert_string_to_list)
    df['tag'] = df['tag'].apply(lambda x : ast.literal_eval(x))

    # 일치하는 태그 개수를 저장할 리스트
    df['tag_match_count'] = df['tag'].apply(lambda tags: len(set(tags) & set(user_tags)))

    # 일치하는 태그 개수와 리뷰 수를 기준으로 정렬 (태그 개수 내림차순 -> 리뷰 수 내림차순)
    sorted_df = df.sort_values(by=['tag_match_count', 'review_count'], ascending=[False, False])

    # 태그 매칭 개수가 0인 행은 제외
    recommended_spots = sorted_df[sorted_df['tag_match_count'] > 0]

    # 결과 출력
    result = recommended_spots[['contentid', 'title', 'cat2', 'cat3', 'firstimage', 'address']].reset_index(
        drop=True).iloc[:10, :]
    result2 = recommended_spots[['contentid', 'title', 'cat2', 'cat3', 'firstimage', 'address']].reset_index(
        drop=True).iloc[10:20, :]

    return result, result2

def famous_tourist_spots(df, topic):
    df = df.copy()
    df['type'] = topic
    if (df['like_count']==0).all():
        return df.sample(min(len(df), 5))[['type','contentid','title','cat2','cat3','firstimage','address','mapx','mapy']]
    else:
        return df.sort_values(['like_count'],ascending=False).head(5)[['type','contentid','title','cat2','cat3','firstimage','address','mapx','mapy']]

# 사용자 온보딩 정보를 가져오는 함수 (예시)
def get_user_onboarding_info(user_id):
    # Query the onboarding_info table to get the user's travelType
    query = f"SELECT travelType FROM onboarding_info WHERE userId = {user_id}"
    df = connect_mysql(query)
    if df.empty:
        # If no onboarding info found for this user, return an empty list or handle appropriately
        return []
    else:
        # Assuming travelType is stored as a JSON string in the database
        travelType_str = df.iloc[0]['travelType']
        # Convert the JSON string to a Python list
        try:
            travelType_list = json.loads(travelType_str)
            return travelType_list
        except json.JSONDecodeError:
            # Handle error if travelType is not valid JSON
            return []

# 좋아요 상태를 추가하는 함수
def add_is_liked_column(df, user_id):
    if df.empty:
        df['is_liked'] = []
        return df

    content_ids = df['contentid'].tolist()

    content_ids_tuple = tuple(content_ids)
    if len(content_ids_tuple) == 1:
        content_ids_tuple += (None,)

    like_query = """
        SELECT contentId
        FROM likes
        WHERE userId = %s AND contentId IN %s
    """

    try:
        connection = pymysql.connect(
            host=MYSQL_HOSTNAME,
            port=MYSQL_PORT,
            user=MYSQL_USERNAME,
            password=MYSQL_PASSWORD,
            database=MYSQL_DATABASE
        )
        df_likes = pd.read_sql(like_query, connection, params=(user_id, content_ids_tuple))
        df['is_liked'] = df['contentid'].isin(df_likes['contentId'])
    except Exception as e:
        print(f"Error fetching likes: {str(e)}")
        df['is_liked'] = False
    finally:
        connection.close()

    return df

@router.get("/main/{user_id}")
async def read_main_items(user_id: int):

    # 사용자 온보딩 정보 가져오기
    user_tags = get_user_onboarding_info(user_id)

    df_fix = connect_mysql("""SELECT * 
                FROM visit_main_fix 
                WHERE firstimage is not null 
                AND firstimage not in ('', ' ', 'None')
                AND contentid is not null
                AND tag is not null""")

    content1_df = df_fix.sample(1)[['contentid', 'title', 'firstimage']]
    content2_df, content4_df = recommend_tourist_spots(user_tags, df_fix)

    # 좋아요 상태 추가
    content2_df = add_is_liked_column(content2_df, user_id)
    content4_df = add_is_liked_column(content4_df, user_id)

    df_sea = df_fix[df_fix['cat3'].isin(['해수욕장', '섬', '해안절경', '등대', '항구/포구'])]
    df_healing = df_fix[df_fix['tag'].apply(lambda x: '힐링' in x)]

    content3_1_df = famous_tourist_spots(df_sea,'바다')
    content3_5_df = famous_tourist_spots(df_healing,'힐링')

    df_festival = connect_mysql(
        """select * from festival_main 
            where cat2='축제' 
            and firstimage is not null 
            and firstimage not in ('',' ', 'None') 
            and contentid is not null
            and eventstartdate > CURDATE()""")
    content3_2_df = famous_tourist_spots(df_festival,'축제')

    df_restaurant = connect_mysql(
        """select * from food_main 
            where cat3 not in ('카페/전통찻집') 
            and firstimage is not null 
            and firstimage not in ('',' ', 'None') 
            and contentid is not null""")

    df_cafe = connect_mysql(
        """select * from food_main 
            where cat3 = '카페/전통찻집' 
            and firstimage is not null 
            and firstimage not in ('',' ', 'None') 
            and contentid is not null""")

    content3_4_df = famous_tourist_spots(df_restaurant,'맛집')
    content3_3_df = famous_tourist_spots(df_cafe,'카페')

    df_hotel = connect_mysql(
        """select * from stay_main 
            where cat3 in ('관광호텔', '콘도미니엄')
            and firstimage is not null 
            and firstimage not in ('',' ', 'None') 
            and contentid is not null""")

    content3_6_df = famous_tourist_spots(df_hotel,'호캉스')

    content3_df = pd.concat([content3_1_df, content3_2_df, content3_3_df,
                             content3_4_df, content3_5_df, content3_6_df],
                            axis=0)

    df_food = pd.concat([df_restaurant, df_cafe], axis=0)
    content5_df = df_food[df_food['summary'].apply(lambda x: '뷰' in x)].sample(1)[
        ['contentid', 'title', 'cat2', 'cat3', 'firstimage', 'address', 'mapx', 'mapy']]

    # 좋아요 상태 추가
    content5_df = add_is_liked_column(content5_df, user_id)

    content6_df = df_fix.sort_values(['like_count', 'review_count'], ascending=[False, False]).head(50).sample(5)[['contentid', 'title', 'firstimage']]

    json_output = {
        "view1": json.loads(content1_df.to_json(orient='records', force_ascii=False)),
        "view2": json.loads(content2_df.to_json(orient='records', force_ascii=False)),
        "view3": json.loads(content3_df.to_json(orient='records', force_ascii=False)),
        "view4": json.loads(content4_df.to_json(orient='records', force_ascii=False)),
        "view5": json.loads(content5_df.to_json(orient='records', force_ascii=False)),
        "view6": json.loads(content6_df.to_json(orient='records', force_ascii=False))
    }

    # JSON 응답을 반환
    return JSONResponse(content=json_output)
