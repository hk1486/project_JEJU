from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, APIRouter
from fastapi.responses import JSONResponse
from typing import List
from pydantic import BaseModel, Field, validator
import os
import pymysql
import pandas as pd
import numpy as np
import ast
from openai import OpenAI

load_dotenv()

app = FastAPI()
router = APIRouter()

# GPT API 클라이언트 초기화
CLIENT = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# MySQL 연결 정보
MYSQL_HOSTNAME = os.getenv('MYSQL_HOSTNAME')
MYSQL_PORT = int(os.getenv('MYSQL_PORT'))
MYSQL_USERNAME = os.getenv('MYSQL_USERNAME')
MYSQL_PASSWORD = os.getenv('MYSQL_PASSWORD')
MYSQL_DATABASE = os.getenv('MYSQL_DATABASE')


# 요청 본문 모델 정의
class RecommendTravelRequest(BaseModel):
    userId: int
    season: str
    duration: str
    travelmate: str
    location: str
    traveltheme: List[str]  # 리스트 형식의 테마
    mapx: float = None  # 사용자가 '내 위치'를 선택한 경우 필요
    mapy: float = None  # 사용자가 '내 위치'를 선택한 경우 필요

# 연령대 및 성별 매핑
AGE_MAPPING = {1: '10대', 2: '20~24세', 3: '25~30세', 4: '31~35세', 5: '36세 이상', 6: 'Unknown'}
GENDER_MAPPING = {1: '남자', 2: '여자', 3: 'Unknown'}

def call_csv():
    df = pd.read_csv('main_total_docent.csv')

    df = df[(df['contentsid'].notnull()) & (df['mapx'].notnull()) & (df['mapy'].notnull()) & (df['tag'].notnull()) & (
        df['summary'].notnull()) & (df['title'].notnull())]
    df = df[~df['cat1'].isin(['추천코스'])]

    return df

# 데이터베이스 연결 함수
def connect_mysql():
    try:
        connection = pymysql.connect(
            host=MYSQL_HOSTNAME,
            port=MYSQL_PORT,
            user=MYSQL_USERNAME,
            password=MYSQL_PASSWORD,
            database=MYSQL_DATABASE
        )
        return connection
    except Exception as e:
        print(f"Database connection error: {str(e)}")
        raise HTTPException(status_code=500, detail="Database connection failed.")


# Function to calculate Euclidean distance between two points
def euclidean_distance(x1, y1, x2, y2):
    return np.sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2)


# Function to filter rows within a given distance without adding a new column
def filter_within_distance(df, mapx_column, mapy_column, target_x, target_y, distance_threshold):
    # Filter rows based on Euclidean distance
    filtered_df = df[df.apply(
        lambda row: euclidean_distance(row[mapx_column], row[mapy_column], target_x, target_y) <= distance_threshold,
        axis=1)]
    return filtered_df


# Function to calculate overlap count between two lists
def overlap_count(list1, list2):
    list1 = ast.literal_eval(list1)

    set1 = set(list1)
    set2 = set(list2)
    return len(set1.intersection(set2))


# Function to get top k rows with highest overlap count
def top_k_overlap(df, tag_column, A, k):
    # Calculate overlap count for each row
    df['overlap_count'] = df[tag_column].apply(lambda x: overlap_count(x, A))

    # Sort the dataframe by overlap_count in descending order
    sorted_df = df.sort_values(by='overlap_count', ascending=False)

    # Check if top-k row has 0 overlap
    top_k_overlap_count = sorted_df.iloc[k - 1]['overlap_count'] if len(sorted_df) >= k else 0

    if top_k_overlap_count == 0:
        filtered_df = []
        # print(f"Warning: The top-{k} entry has 0 overlapping elements with the given tag list.")

    # Filter rows with overlap_count greater than or equal to top-k overlap count
    else:
        filtered_df = sorted_df[sorted_df['overlap_count'] >= top_k_overlap_count]

    return filtered_df


# 후보군이 최소 k개 있는지 확인 (k=60), m개 이상의 겹치는 태그가 있는지 확인
def find_locations_within_k(df, target_tag_list, mapx_column, mapy_column, target_x, target_y, k, m,
                            initial_threshold=0.045, step=0.009, max_threshold=0.5, max_iterations=10):
    distance_threshold = initial_threshold
    iterations = 0

    while distance_threshold <= max_threshold and iterations < max_iterations:
        filtered_df = filter_within_distance(df, mapx_column, mapy_column, target_x, target_y, distance_threshold)
        # print(f"Found {len(filtered_df)} locations within {distance_threshold} distance")

        if len(filtered_df) >= k:
            result_df = top_k_overlap(filtered_df, 'tag', target_tag_list, m)
            # print(f"Found {len(result_df)} locations with overlap")

            if len(result_df) >= m:
                print(f"Found {len(result_df)} locations with at least {m} overlapping elements")
                return result_df, distance_threshold

        # Increase the distance threshold
        distance_threshold += step
        iterations += 1
        # print(f"Increasing distance threshold to {distance_threshold}, iteration {iterations}")

    print(f"Stopped after {iterations} iterations or reaching the max distance threshold.")
    return None, distance_threshold  # Return None if no valid result is found

travel_mate_with_postposition_dict = {'혼자': '혼자', '친구': '친구와 함께', '연인': '연인과 함께', '가족': '가족과 함께', '아이': '아이와 함께'}

def recommend_travel_spots(age: str, sex: str, season: str, duration: str, travel_mate: str, candidates_df, MODEL: str,
                           client):
    title_list_with_summary = []
    for i, row in candidates_df.iterrows():
        title_list_with_summary.append(row['title'] + ': ' + row['summary'])
    travel_explain_total_text = '\n'.join(title_list_with_summary)
    travel_mate_with_postposition = travel_mate_with_postposition_dict[travel_mate]
    system_prompt = """한국 관광객에게 제주도 여행지를 특별하게 소개해줄거야. 나이와 성별에 맞게 여행코스를 짜주려해. 여행이 하나의 이야기가 될 수 있도록, 여행지들을 추천해주고, 내가 주는 여행지에 대한 설명을 참고해서 추천 여행코스를 하나의 스토리 처럼 만들어줘. 즉, 추천 여행코스를 쭉 알려주고, 이 여행코스를 하나의 이야기로 만들어서 알려주는 것까지 하면 돼.

    여행관광지에 대한 설명은 다음과 같아: """

    #     print(f"""여행자는 MBTI가 {mbti}로, {mbti_descriptions[mbti]} 여행자에게 알맞은 여행지를 추천해줘. 여행지와 여행지에 대한 설명을 줄게. 너는 해당 여행관광지의 설명을 보고, 다음과 같은 성향의 사람에게 알맞은 관광지들로 하나의 멋진 여행 코스를 작성해줘. 추천 관광지의 내용들을 토대로 멋진 하나의 스토리를 작성해서 여행자로 하여금 여행가고 싶게 만들어줘. 너무 부담스럽게 말고 담백하고 신선하게 여행코스 추천해줘.

    # 여행지와 그에 대한 설명은 다음과 같아:
    # {travel_explain_total_text}""")
    #     return True
    total_message_with_prompt = [
        {
            "role": "system",
            "content": system_prompt,
        },
        {
            "role": "user",
            "content": f"""여행자는 나이: {age} 성별: {sex} 한국인으로, 이번{season}에 {travel_mate_with_postposition} 제주도로 {duration} 여행을 가. 여행자에게 알맞은 여행지를 추천해줘. 여행지와 여행지에 대한 설명을 줄게. 너는 해당 여행관광지의 설명을 보고, 다음과 같은 성향의 사람에게 알맞은 관광지들로 하나의 멋진 여행 코스를 작성해줘. 추천 관광지의 내용들을 토대로 멋진 하나의 스토리를 작성해서 여행자로 하여금 여행가고 싶게 만들어줘. 너무 부담스럽게 말고 신선하게 여행코스 추천해줘.

여행지와 그에 대한 설명은 다음과 같아. 각각 여행지에 대한 설명에 추가로, 멋진 여행스토리를 만들어줘. 스토리는 하나의 이야기처럼 잘 만들어줘. 다른 인사말 같은거 하지말고, 바로 스토리에 대해서 이야기해줘. 그리고 강조할 문장이나 단어에는 볼드체 할 수 있도록 정규식으로 표시해줘. 뻔한 이야기는 하지말고, 각 관광지가 갖고있는 전설과 역사와 같이 알면 더 흥미롭게 여행할 수 있는 내용들을 포함해서 스토리를 만들어줘. 역사와 전설에 대한 이야기를 통해 여행자에게 감동을 주는 스토리로 만들어줘. 여행자가 여행지에 도착했을 때, 그곳의 분위기와 전설을 떠올리며 여행을 즐길 수 있도록 스토리를 만들어줘.
예시는 다음과 같아:

아침 햇살이 제주도를 따뜻하게 감싸는 가운데, 곽지해수욕장으로 향한다. 이곳에는 오래전 **모래에 묻힌 옛 마을**에 대한 전설이 전해져 내려온다. 강풍에 휩쓸려 마을이 모래 속으로 사라졌다는 이야기는 지금도 이 해변을 찾는 이들에게 신비로운 상상을 불러일으킨다. 여행자는 그 전설을 떠올리며, 마치 모래 아래에 잠들어 있는 옛 마을의 흔적을 느끼듯 해변에 발을 디딘다. 물결이 발목을 스치며 지나가자, 잠시 모든 걱정을 잊게 해주는 편안함이 느껴진다. 해변의 끝자락에는 **과물노천탕**이 있어, 바다에서 즐겁게 논 후 따뜻한 물로 몸을 씻으며 **여유로운 시간**을 만끽한다.
다음은 **애월 바다의 아름다운 풍경**이 펼쳐진 제주의 대표적인 트레킹 코스인 **제주올레 16코스**로 향한다. **고내에서 구엄까지** 이어지는 이 길은 **쪽빛 바다**와 **하얀 소금기**, **나무 그늘이 만들어주는 조화로움**이 **진정한 평화**를 선사한다. 이곳에서 **마음의 평화**를 느끼며 **걸음을 재촉**한다.
**점심시간**, **애월한담공원**으로 가서 **바다를 바라보며 여유롭게 산책**을 즐기러 간다. **바다를 배경**으로 한 **물허벅 여인상**을 보러간다. 예로부터 제주 여성들은 **물**이 귀한 섬에서 **물허벅**을 머리에 이고 우물과 집을 오가며 **가족의 생명**을 지켰다. 그 과정에서 **서로의 짐을 덜어주고**, 힘든 동료를 격려하며 **강한 유대감**을 쌓았다고 한다. 한 전설에 따르면, 어느 날 **무거운 물허벅**을 이고 힘겹게 걸어가던 여인에게 **하늘에서 신비한 존재**가 내려와 물허벅을 **가볍게 해주었다**고 전해진다. 이곳에서 그 옛날 **강인한 제주 여인들**의 모습을 떠올리며, 여행자는 그들의 **강한 의지**와 **자연과의 조화**를 마음에 새기며 발걸음을 내디딘다. 이후 **인근 카페거리**에서 **특유의 제주음식**을 맛보며, 다시 한번 **자연의 아름다움**을 마음에 새긴다.
**소화가 잘 되고**, **나쁜 기운을 쫓아줄 고기국수**로 인정받은 **꽁순이네**에서의 점심은 어떨까? **진하고 부드러운 국물**이 **제주에서만 느낄 수 있는 특별함**을 더해준다. 식사를 마치고 **애월 해안**에서 **한담해안산책로**를 따라가며, **파도 소리**가 속삭이듯 발걸음을 맞이한다. 전해지는 이야기에 따르면, 오래전 이곳에서 **한 어부가 바다의 신**과 **대화를 나누었다**고 한다. **거친 파도**에 시달리던 마을을 위해 어부는 바다와 대화를 시도했고, 그의 **진심이 전해지자** 바다는 잔잔해져 **마을에 풍요**가 돌아왔다고 한다. **산책로를 걸으며** 그 어부의 **발자취**를 따라가다 보면, 어느새 **마음도 차분해지고 바다의 평온함**이 온몸에 스며드는 듯한 기분을 느낄 수 있다.
오후에는 **귀덕바다투명카약 체험**을 통해 **제주 바다 속 풍경**을 가까이에서 느껴본다. **투명한 카약** 아래로 보이는 **다채로운 수중 생물**들이 **하늘과 바다의 경계**를 허물고, **즐거움이 두 배**로 늘어난다. 카약을 타고 **물 소리**를 들으며 **소소한 행복**을 체험한 후, **한담해변 산책로**로 다시 돌아가 **일몰**을 감상하는 것이 이날의 **하이라이트**. **붉게 물드는 하늘**을 바라보며 **아름다운 제주에서의 순간**을 마음에 새긴다.
저녁에는 **선운정사**로 이동해 **노을빛이 비친 연꽃등의 경관**을 즐긴다. **차분한 경전 소리**와 함께하는 **불빛의 향연**은 **하루의 피로**를 잊게 해주며, 그렇게 **가벼운 마음**으로 **제주에서의 하루**를 마감하기에 적합한 장소이다.
하루를 마치고, 여행자는 **제주에서의 특별한 추억**을 안고 돌아간다. 각 여행지에서 **소중한 소통**과 **자연의 정수**를 경험하며, **마음에 따뜻함**을 더할 수 있었던 특별한 날이었기를, **제주에서의 하룻밤**은 오랫동안 **그리움**으로 남기를 바란다.

여행지와 여행지 설명:
{travel_explain_total_text}""",
        }
    ]
    response = client.chat.completions.create(
        messages=total_message_with_prompt,
        model=MODEL,
        temperature=1.0,
    )
    gpt_response = response.choices[0].message.content
    return gpt_response

@router.post("/recommend_travel")
async def recommend_travel(request: RecommendTravelRequest):
    try:
        # Location 데이터 정의
        locations = {
            "서귀포시": {"위도": 33.2531, "경도": 126.5595},
            "제주국제공항": {"위도": 33.5104, "경도": 126.4914},
            "제주시": {"위도": 33.4996, "경도": 126.5312},
            "성산일출봉": {"위도": 33.4580, "경도": 126.9411},
            "한라산": {"위도": 33.3625, "경도": 126.5339},
            "협재해수욕장": {"위도": 33.3948, "경도": 126.2396},
            "중문관광단지": {"위도": 33.2500, "경도": 126.4100},
            "우도": {"위도": 33.5020, "경도": 126.9548},
            "섭지코지": {"위도": 33.4247, "경도": 126.9242},
            "천지연폭포": {"위도": 33.2452, "경도": 126.5655},
            "함덕해수욕장": {"위도": 33.5434, "경도": 126.6728},
            "애월": {"위도": 33.4658, "경도": 126.3272}
        }

        # 1. 유저 정보를 온보딩 테이블에서 조회
        connection = connect_mysql()
        with connection.cursor() as cursor:
            cursor.execute("SELECT ageRange, gender FROM onboarding_info WHERE userId = %s", (request.userId,))
            user_data = cursor.fetchone()
        if user_data is None:
            raise HTTPException(status_code=404, detail="User not found")

        age_numeric, gender_numeric = user_data

        # 2. 연령대와 성별을 숫자에서 문자로 매핑
        age = AGE_MAPPING.get(age_numeric, "Unknown")
        gender = GENDER_MAPPING.get(gender_numeric, "Unknown")

        # 3. 여행지 추천 로직 실행
        df = call_csv()
        if request.location != '내 위치':
            target_x, target_y = locations[request.location]["경도"], locations[request.location]["위도"]
        else:
            target_x, target_y = request.mapx, request.mapy

        filtered_df, distance = find_locations_within_k(df, request.traveltheme, 'mapx', 'mapy', target_x, target_y, 50, 30)
        if filtered_df is None or filtered_df.empty:
            raise HTTPException(status_code=404, detail="No travel spots found")

        result = recommend_travel_spots(age, gender, request.season, request.duration, request.travelmate, filtered_df, "gpt-4o-mini", CLIENT)

        return {"recommendation": result}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        connection.close()

