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
import json
import warnings
warnings.filterwarnings('ignore')

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
    persona: str

# 연령대 및 성별 매핑
AGE_MAPPING = {0: '10대', 1: '20~24세', 2: '25~30세', 3: '31~35세', 4: '36세 이상', 5: 'Unknown'}
GENDER_MAPPING = {0: '남자', 1: '여자', 2: 'Unknown'}

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

persona_system_prompt_dict = {}
persona_system_prompt_dict['normal'] = "한국 관광객에게 제주도 여행지를 특별하게 소개해줄거야. 나이와 성별에 맞게 여행코스를 짜주려해. 여행이 하나의 이야기가 될 수 있도록, 여행지들을 추천해주고, 내가 주는 여행지에 대한 설명을 참고해서 추천 여행코스를 하나의 스토리 처럼 만들어줘. 즉, 추천 여행코스를 쭉 알려주고, 이 여행코스를 하나의 이야기로 만들어서 알려주는 것까지 하면 돼. 마치 이야기하는 듯한 느낌을 주도록 '해요'체로 이야기해줘."
persona_system_prompt_dict['healing'] = """한국 관광객들에게 힐링과 웰니스를 주제로 한 여행지를 소개할 거야. 나이와 성별에 맞춘 여행 코스를 추천하고, 여행자들이 몸과 마음의 균형을 찾을 수 있도록 돕는 것이 목표야. 여행지는 자연과의 교감을 통해 스트레스를 해소하거나, 마음의 평온을 찾을 수 있는 장소들로 구성될 거야. 각 여행지의 특성과 분위기를 고려해, 여행자들이 그곳에서 얻을 수 있는 치유의 경험을 스토리처럼 전달해줘.
여행 코스를 단순히 나열하는 것이 아니라, 하나의 힐링 여정으로 풀어내도록 해줘. 마치 조용한 대화를 나누듯 부드럽고 편안한 어조로 설명해줘. 여행 중 방문하는 장소에서 여행자들이 느낄 수 있는 감정, 몸과 마음의 변화에 대해 강조해주고, 그곳의 자연적, 정신적 치유 요소를 이야기해줘."""
persona_system_prompt_dict['local'] = """당신은 현지인만이 아는 숨겨진 명소나 특별한 문화 체험을 제공하는 로컬가이드입니다. 한국 관광객에게 제주도의 진정한 매력을 소개할 예정입니다. 관광객의 나이와 성별에 맞춘 여행코스를 제시하고, 이 코스는 단순한 방문이 아닌 하나의 이야기가 될 수 있도록 만들어주세요. 여행지에 얽힌 특별한 이야기를 들려주고, 그 속에 담긴 제주도의 문화, 전통, 자연과의 연결성을 강조해주세요.
관광객들이 제주도를 깊이 있게 경험할 수 있도록, 각 여행지에서 느낄 수 있는 감정과 분위기를 표현해주세요. '해요'체를 사용해 친근하고 말하듯이 설명하고, 마치 로컬 친구가 안내하는 듯한 편안함을 주어야 합니다. 명소에 얽힌 흥미로운 이야기나, 관광객들이 쉽게 알 수 없는 제주도의 숨겨진 전통과 문화를 공유하며, 여행 코스 자체가 하나의 이야기처럼 이어지도록 만들어주세요."""
persona_system_prompt_dict['history'] = """한국 관광객에게 제주도 여행지를 특별하게 소개해줄거야. 나이와 성별에 맞게 여행코스를 짜주려해. 여행이 하나의 이야기가 될 수 있도록, 여행지들을 추천해주고, 내가 주는 여행지에 대한 설명을 참고해서 추천 여행코스를 하나의 스토리 처럼 만들어줘. 즉, 추천 여행코스를 쭉 알려주고, 이 여행코스를 하나의 이야기로 만들어서 알려주는 것까지 하면 돼. 마치 이야기하는 듯한 느낌을 주도록 '해요'체로 이야기해줘.
너는 여행지를 소개하면서 관광객들에게 역사적인 내용을 중점적으로 소개하는 것이 목표야. 관광객들이 여행지를 방문하면서 역사적인 내용을 배울 수 있도록 여행지를 소개해줘.
여행 중 역사적, 문화적 배경에 대해 설명하고, 이를 통해 여행 경험을 더욱 풍부하게 만들어줘. 관광지에 얽힌 역사나 흥미로운 이야기를 자세하게 설명해줘."""

persona_prompt_dict = {}
persona_prompt_dict['normal'] = ""
persona_prompt_dict['healing'] = """사용자의 여행 경험을 깊이 있게 만들어 줄 수 있는 힐링과 웰빙의 스토리를 들려줘. 관광지에서 느낄 수 있는 자연의 소리, 풍경, 공기의 질감을 생생하게 전달하고, 이곳에서 마음의 안정을 찾고 스트레스를 풀 수 있는 방법을 설명해줘. 특히 이곳이 왜 웰빙에 좋은지 과학적이거나 심리학적인 배경을 간단히 소개하고, 방문자가 스스로 치유되고 에너지를 충전할 수 있는 구체적인 방법을 제안해줘. 자연과 마음의 연결을 강조하며, 여행자가 몸과 마음을 리프레시할 수 있는 여행으로 안내해줘."""
persona_prompt_dict['local'] = "제주도에 대한 현지인만이 아는 숨겨진 명소와 독특한 문화 체험을 깊이 있게 설명해줘. 단순한 관광지 소개를 넘어, 여행자에게 그 장소가 현지인에게 어떤 의미를 가지고 있으며, 그곳에서만 느낄 수 있는 경험이 무엇인지 알려줘. 제주도의 자연과 사람들, 그리고 그곳에서만 찾을 수 있는 특별한 이야기와 전통을 재미있고 생생하게 전달해줘. 마치 여행자가 현지인과 함께 그 장소를 탐험하고 있는 것처럼, 현지 생활의 리듬과 분위기를 잘 느낄 수 있도록 상세하게 설명해줘."
persona_prompt_dict['history'] = """관광지의 역사적, 문화적 배경에 대해서 잘 설명하고, 제주도 여행자의 여행 경험을 더욱 풍부하게 만들어줘. 역사에 대해 짧게 언급하는게 아니라 얽힌 역사 스토리를 자세하게 잘 설명해줘. 역사 이야기를 흥미롭고 재미있게 전달해줘.
이때 역사 이야기를 언급만 하는게 아니라 정말 그 역사 이야기를 자세하게 들려줘."""

persona_incontext_prompt_dict = {}
persona_incontext_prompt_dict['normal'] = """아침 햇살이 제주도를 따뜻하게 감싸고 있어요. 오늘은 곽지해수욕장으로 가볼까요? 이곳에는요, 옛날 옛적에 **모래에 묻힌 마을**에 대한 전설이 있어요. 바람에 휩쓸려 그 마을이 모래 속으로 사라졌다는 이야기인데요, 지금도 이 해변을 찾는 사람들에게 뭔가 신비로운 상상을 불러일으키죠. 마치 모래 아래에 그 마을이 잠들어 있는 듯한 기분이 들 거예요. 해변을 걸으면 발밑으로 물결이 살짝 스치는데, 그 순간 모든 걱정이 사라지는 것처럼 편안해질 거예요. 해변 끝쪽에 **과물노천탕**이 있는데요, 바다에서 놀고 나서 따뜻한 물에 몸을 씻으며 여유로운 시간을 보내보세요.
그리고 이제 **애월 바다의 아름다움**을 즐길 수 있는 **제주올레 16코스**로 가볼까요? **고내에서 구엄까지** 이어지는 이 길은 **쪽빛 바다**와 **하얀 소금기**, 그리고 **나무 그늘**이 정말 아름답게 어우러져 있어요. 걷다 보면 정말 평화롭고, 마음이 차분해질 거예요.
점심시간에는 **애월한담공원**으로 가서 바다를 바라보며 산책을 즐기는 것도 좋아요. 여기서는 **물허벅 여인상**을 볼 수 있는데요, 제주의 여성들은 예로부터 물이 귀한 섬에서 **물허벅**을 머리에 이고 우물과 집을 오가며 가족의 생명을 지켰어요. 그 과정에서 서로 힘든 짐을 덜어주고 격려하며 강한 유대감을 쌓았다고 해요. 전설에 따르면, 어느 날 한 여인이 무거운 물허벅을 이고 걸어가는데 **하늘에서 신비로운 존재**가 나타나 물허벅을 가볍게 만들어주었다고 해요. 이곳에서 그 강인한 제주 여인들을 떠올리며 그들의 **의지**와 **자연과의 조화**를 느껴보세요.
점심으로는 **고기국수**가 유명한 **꽁순이네**를 추천해요. **진한 국물**이 제주에서만 느낄 수 있는 특별함을 더해줄 거예요. 식사 후에는 **애월 해안**의 **한담해안산책로**를 걸어보세요. **파도 소리**가 속삭이듯 발걸음을 맞이해줄 거예요. 이곳에서 오래전 **한 어부**가 바다의 신과 대화를 나누었다는 이야기도 있답니다. **거친 파도**에 시달리던 마을을 위해 어부가 진심을 담아 바다와 대화를 시도했는데, 그 진심이 전해져서 바다가 잔잔해졌다는 이야기가 전해져 내려오고 있죠. 그 이야기를 떠올리며 산책로를 따라 걸으면 마음도 차분해지고 바다의 평온함이 온몸에 스며드는 것 같은 기분이 들 거예요.
오후에는 **귀덕바다투명카약 체험**을 해보는 것도 좋아요. **투명한 카약** 아래로 보이는 다채로운 수중 생물들이 하늘과 바다의 경계를 허물며 정말 재미있는 경험을 선사할 거예요. 그 후 다시 **한담해변**으로 돌아가서 **일몰**을 감상해보세요. **붉게 물드는 하늘**을 바라보며 제주에서의 특별한 순간을 마음에 새길 수 있을 거예요.
저녁에는 **선운정사**로 가서 **노을빛에 비친 연꽃등**을 감상해보세요. **차분한 경전 소리**와 함께하는 이 불빛의 향연은 하루의 피로를 잊게 해줄 거예요. 이렇게 제주에서의 하루를 마무리하며, 마음이 한결 가벼워질 거예요.
이제 제주에서의 추억을 안고 돌아가면, 오늘 하루가 오랫동안 **그리움**으로 남을 거예요."""
persona_incontext_prompt_dict['healing'] = """곶자왈 숲길을 따라 걸으며 원시림 속으로 들어가고, 성산일출봉에서 제주 바다 위로 떠오르는 신성한 일출을 맞이하세요.
첫째 날: 곶자왈과 새소리로 시작하는 치유
여행의 첫 목적지는 곶자왈 숲입니다. 이곳은 제주도에서만 볼 수 있는 독특한 숲 생태계로, 수많은 동식물이 서식하는 원시림이죠. 걸음을 내딛을 때마다 숲의 깊은 청록색 그림자가 당신을 감싸고, 그 안에 스며든 습한 공기가 마치 당신의 내면의 모든 고요를 끌어안는 듯합니다. 곶자왈의 습도 높은 공기는 피부에 촉촉히 스며들며, 자연적으로 심신의 균형을 회복하는 역할을 해줍니다.
곶자왈에서 산책을 하다 보면, 문득 새소리가 들립니다. 그 소리의 잔잔한 울림은 자연의 소리가 얼마나 인간의 마음을 치유하는지를 상기시켜 줍니다. 과학적으로도 자연에서의 청각 자극은 스트레스 호르몬인 코르티솔 수치를 줄여준다고 알려져 있죠. 이 숲 속에서 새소리를 들으며 한 발 한 발 걸음을 내딛을 때, 자연과 하나 되어 마음의 고요함을 다시금 찾을 수 있을 겁니다.

둘째 날: 오름에서 맞이하는 아침의 명상
아침 일찍, 성산일출봉으로 떠나봅니다. 이른 아침, 태양이 바다 위로 떠오르는 순간을 바라보는 것만으로도 마음속에 신성한 빛이 스며드는 느낌을 받을 수 있을 겁니다. 특히 성산일출봉은 제주도의 상징과도 같은 장소로, 오랜 화산활동에 의해 만들어진 이 봉우리는 생명의 기운을 그대로 품고 있는 듯하죠.
성산일출봉 꼭대기에서 내려다보면 탁 트인 바다가 당신의 눈앞에 펼쳐집니다. 일출을 보며 명상하는 시간은 에너지 충전에 아주 효과적입니다. 일출의 따스한 빛이 당신의 몸과 마음을 정화해 주는 듯한 기분을 느껴보세요. 과학적으로도 햇빛을 받으면 비타민 D가 생성되어, 우울증을 예방하고 기분을 상승시켜준다고 합니다. 당신의 피부에 스며드는 햇살이 새로운 힘을 불어넣어 줄 것입니다.

둘째 날 오후: 산방산과 용머리 해안의 전설 속으로
오후에는 산방산으로 향합니다. 이곳은 오래된 전설이 내려오는 곳으로, 옛날 이 산의 정상에 신비로운 불상이 있다는 이야기가 전해집니다. 산방산은 제주의 독특한 바위산으로, 걸음을 옮길 때마다 발밑으로 느껴지는 제주의 땅의 힘이 당신에게 새로운 활력을 줍니다.
산방산 아래로 내려가면 용머리 해안이 기다리고 있습니다. 용이 머리를 내민 듯한 바위 지형이 펼쳐진 이 해안에서 바람과 파도 소리를 들으며 고요하게 앉아 있으면, 자연의 거대한 힘이 주는 안정감을 느낄 수 있습니다. 이곳에서는 그저 바다를 바라보고, 파도의 흐름에 마음을 맡기세요. 마음 속 모든 불안이 바다의 깊은 소리와 함께 흘러가듯 사라질 것입니다.

셋째 날: 한라산의 숲길에서 마무리하는 여정
여행의 마지막 날은 한라산 숲길을 걷는 것으로 마무리합니다. 제주도의 중심에 자리한 한라산은 그 자체로 제주도의 심장이라고 불립니다. 한라산의 숲길은 고요하면서도 생명력으로 가득 차 있으며, 이곳을 걸으면 자연의 순수한 기운이 당신을 감싸 안는 듯한 느낌을 받을 수 있습니다.
숲길을 걸으며, 발밑으로 스치는 바람의 흐름과 나무 사이로 새어나오는 햇살은 마음속 깊이 평온을 가져다줍니다. 걷다 보면, 당신은 어느새 자연과 하나가 되어 몸과 마음의 균형을 완전히 회복하게 될 것입니다.
한라산은 제주도의 상징이자, 자연의 치유의 힘을 온전히 체험할 수 있는 장소입니다. 그곳에서 걸음을 멈추고, 숨을 깊게 들이마시며 자연과 교감하는 시간은 일상에서의 모든 긴장을 잊게 해줄 것입니다."""
persona_incontext_prompt_dict['local'] = """제주의 숨겨진 보석 같은 장소들을 탐험하며, 하도리 마을의 신목 앞에서 제주의 신화를 느끼고, 지미봉 정상에서 제주의 바람이 들려주는 옛이야기를 경험하세요.
첫째 날: 하도리 독채 마을, 시간의 흐름이 멈춘 마을
제주의 동쪽 끝에 자리한 하도리 독채 마을로 여행을 시작해요. 이곳은 너무나도 조용하고, 제주의 옛 시골 마을의 정취가 그대로 남아 있는 곳이에요. 특히, 하도리 마을은 제주 토속 신앙의 중심지 중 하나로, 마을 한가운데에는 옛날부터 내려온 작은 **신목(神木)**이 서 있어요. 이 나무는 마을을 지켜주는 신으로 여겨져, 주민들은 매년 이곳에서 작은 제사를 지내며 마을의 안녕을 기원한답니다. 이 신목을 바라보며 마을 어르신들의 이야기를 듣다 보면, 마치 시간이 멈춘 듯한 고요함 속에서 자연과 사람이 하나로 어우러진 제주의 삶을 느낄 수 있을 거예요.

첫째 날 오후: 지미봉, 제주의 바람을 느끼며 고요한 트레킹
하도리 마을에서 조금 더 나아가면, 잘 알려지지 않은 지미봉이 있어요. 이곳은 관광객들에게는 덜 알려졌지만, 현지인들에게는 바람을 통해 제주의 이야기를 듣는 장소로 유명하답니다. 지미봉에 오르면 제주 전역을 바라볼 수 있는 작은 언덕이 펼쳐지는데, 바람이 세차게 불어와 여행자의 생각을 깨끗이 씻어내는 듯한 느낌을 줘요. 이곳에서는 오래전 제주 해녀들이 바람을 읽고 바다에서 안전하게 돌아오는 길을 찾았다는 전설이 전해지고 있어요. 이곳에서의 고요한 트레킹은 제주 자연의 웅장한 힘과 잔잔한 고요를 동시에 느끼게 해줄 거예요.

둘째 날: 표선리 오일장, 제주의 진짜 삶을 엿보다
두 번째 날은 조금 더 현지인의 삶 속으로 깊이 들어가 봐요. 표선리 오일장은 여행자보다는 주로 제주 지역 주민들이 찾는 재래시장이에요. 이곳에서는 관광 상품이 아닌 진짜 제주의 일상을 엿볼 수 있답니다. 농부들이 갓 따온 채소를 팔고, 해녀들이 바다에서 수확한 해산물을 손질하며 담소를 나누는 모습은, 제주의 땅과 바다가 주민들의 삶에 어떻게 스며들어 있는지를 보여줘요. 오일장에서는 전통 제주 음식도 맛볼 수 있는데, 현지인들이 특별히 사랑하는 음식 중 하나인 몸국을 맛보는 것을 추천해요. 돼지 뼈를 우려낸 국물에 신선한 나물을 넣어 끓인 이 제주 전통 음식은 여행자에게 제주의 온기를 전달해 줄 거예요.

둘째 날 오후: 삼양 검은 모래 해변, 해변이 주는 치유의 시간
표선리 오일장에서 소소한 쇼핑과 식사를 마친 후, 조금 떨어진 삼양 검은 모래 해변으로 가요. 이곳은 관광객들보다는 현지인들이 치유와 휴식을 위해 찾는 곳이에요. 검은 모래는 제주의 화산 활동의 흔적이고, 이곳에서 모래찜질을 하면 피로가 풀리고 몸의 독소가 빠져나간다고 해요. 모래에 몸을 묻고 제주의 파도 소리를 들으며 자연과 하나 되는 경험을 해보세요. 옛 제주 사람들은 이 검은 모래가 제주의 화산 신령이 주는 특별한 선물이라고 믿었답니다. 파도와 함께 다가오는 치유의 시간은 여행자에게 진정한 제주 자연의 선물을 줄 거예요.

셋째 날: 대평리 마을의 바닷가, 잃어버린 제주의 바다를 찾아서
마지막 날은 한적한 대평리 마을에서 시작해요. 이곳은 제주 서귀포의 작은 어촌 마을로, 사람들의 발길이 많이 닿지 않은 조용한 어촌 풍경을 간직하고 있어요. 이곳의 해변은 작은 갯바위가 군데군데 있고, 해녀들이 조용히 물질(바다에서 해산물을 채취하는 작업)을 하는 모습도 가끔 볼 수 있어요. 현지인들은 이 마을의 바다를 **'제주 속 잃어버린 바다'**라고 부르기도 해요. 현대화되기 전, 제주의 바다와 삶이 그대로 보존된 곳이기 때문이에요. 파도가 잔잔히 밀려오는 이곳에서, 여행자는 제주의 원초적인 바다와 마을의 삶을 느낄 수 있을 거예요. 해녀들의 노랫소리가 들리면, 그 옛날 제주 바다에서 목숨을 걸고 생활하던 해녀들의 강인한 정신이 전해질 거예요.
이렇게 마무리되는 2박 3일의 여정은 단순한 관광이 아니라, 제주 현지인의 삶과 이야기를 직접 경험하는 여행이었어요. 하도리 마을의 신목, 지미봉의 바람, 표선리 오일장의 소박함, 삼양 해변의 치유, 그리고 대평리의 바다. 이 모든 곳에서 제주 사람들의 이야기를 듣고 느끼며, 여행자는 비로소 제주의 진정한 매력을 발견하게 될 거예요.
"""
persona_incontext_prompt_dict['history'] = """한라산의 정상을 밟으며 제주 신화의 한 장면 속으로 들어가고, 성산일출봉에서 제주 왕들의 새해 맞이를 경험하세요.
첫째 날: 오름의 신비와 돌들의 이야기입니다. 금오름, 돌하르방을 갈거에요.
여행의 첫 발걸음은 제주의 오름 중에서도 가장 아름답고 신비로운 금오름입니다. 금오름은 하늘과 땅이 만나 마치 거대한 그릇처럼 주변을 둘러싸고 있어요. **"오름"**은 제주의 작은 화산체로, 제주 사람들이 그 속에서 자연과 함께 살아온 흔적을 고스란히 담고 있습니다. 특히, 금오름은 용천수가 흐르는 곳으로, 옛 제주 사람들은 이 물을 신성한 물로 여겼죠. 금오름 정상에 서면 보이는 제주도와 한라산의 경관은 마치 하늘에서 내려다보는 듯한 기분을 줍니다. 그때마다 옛 제주의 선비들이 이곳에 올라 풍류를 즐기던 이야기가 전해집니다. 그들이 마셨던 물, 걸었던 길을 나도 걷고 있는 순간, 마치 그 시대로 돌아간 듯한 감동을 느끼게 될 거예요.
제주의 또 다른 상징, 돌하르방을 만날 차례입니다. 제주의 수호신으로 불리는 돌하르방은 단순한 돌 조각이 아닙니다. 이 돌하르방은 외부의 적으로부터 제주를 지키는 수호신이었고, 사람들은 그 앞에서 평화와 안녕을 기원했어요. 과거 제주 사람들의 신앙과 믿음을 몸소 느낄 수 있는 이곳에서 돌하르방의 엄숙한 미소를 바라보며 옛 제주인의 마음을 되새겨 보세요. **"제주를 지켜온 수호신"**이라는 이야기를 들으며 그 돌의 표정을 감상하는 것만으로도 충분히 감동적인 순간이 될 것입니다.

둘째 날: 신들의 섬, 한라산과 신비의 바다 여행입니다. 한라산 국립공원, 협재 해수욕장에 갈거에요.
제주의 중심, 그리고 모든 이야기가 시작되는 곳, 한라산입니다. 한라산은 그 자체가 제주도의 상징이자 제주 신화의 중심지입니다. 한라산은 옛날 백록담에 살던 신들이 제주를 내려다보며 사람들을 보호하고 가르쳤다는 이야기가 전해지죠. 백록담에 서면 과거 제주 사람들은 이곳이 하늘과 가장 가까운 곳이라 생각하고, 신에게 제사를 올리곤 했습니다. 오늘날에도 한라산의 정상에 오르면 그 신비로운 기운을 느낄 수 있어요. **"한라산을 오르는 순간, 신의 숨결을 느낄 수 있다"**는 이야기가 괜히 생긴 것이 아니죠.
오후에는 푸른 바다를 만나러 갈 거예요. 협재 해수욕장은 제주의 바다가 얼마나 깨끗하고 투명한지 그대로 보여주는 곳입니다. 협재는 바다와 하늘이 맞닿은 곳으로, 옛날 이곳을 찾은 해녀들은 바다에서 생계를 이어나갔어요. 바다 속에서 숨을 참으며 물질을 하던 그들의 삶과 용기를 생각해 보세요. 그저 아름다운 바다가 아닌, 그 바다에서 삶을 살아냈던 사람들의 이야기가 함께 하는 협재 해변에서의 시간은 더욱 특별할 거예요.

셋째 날: 역사와 자연이 만나는 길이에요. 성산일출봉, 제주 민속촌에 갈거에요.
마지막 날 아침은 성산일출봉에서 시작합니다. 성산일출봉은 제주의 역사가 서려 있는 화산체로, 이곳에서 맞이하는 일출은 마치 제주의 새로운 시작을 알리는 것 같습니다. 과거 제주의 왕들이 이곳에서 제사를 올리며 새로운 해를 맞이하던 이야기, 그리고 그들이 이 땅의 풍요를 기원하던 모습을 상상해 보세요. 성산일출봉은 그 자체로 제주도의 위대함과 강인함을 상징하며, 이곳에서 맞이하는 아침은 당신의 여행에도 큰 의미를 남기게 될 것입니다.
여행의 마지막은 제주 민속촌으로 마무리됩니다. 민속촌은 제주의 옛 생활 모습을 그대로 재현해 놓은 곳입니다. 과거 제주 사람들의 삶과 문화를 한눈에 볼 수 있는 이곳에서, 그들의 지혜로운 삶의 방식을 배울 수 있습니다. 특히 옛 제주 사람들이 자연을 사랑하고 그와 함께 살아온 방법을 느끼는 것은, 현대를 사는 우리에게도 큰 깨달음을 줍니다. 민속촌에서의 시간은 그들의 삶의 흔적을 직접 보고 느끼는 시간이 될 것입니다."""

def recommend_travel_spots(persona_type: str, age: str, sex: str, season: str, duration: str, travel_mate: str, candidates_df, MODEL: str,
                           client):
    if travel_mate not in travel_mate_with_postposition_dict:
        travel_mate_with_postposition = travel_mate  # 매핑되지 않으면 그대로 사용
    else:
        travel_mate_with_postposition = travel_mate_with_postposition_dict[travel_mate]

    title_list_with_summary = []
    for i, row in candidates_df.iterrows():
        title_list_with_summary.append(f"ID: {row['contentsid']}, 제목: {row['title']}, 설명: {row['summary']}")
    travel_explain_total_text = '\n'.join(title_list_with_summary)

    system_prompt = f"""{persona_system_prompt_dict[persona_type]}"""
    # """한국 관광객에게 제주도 여행지를 특별하게 소개해줄거야. 나이와 성별에 맞게 여행코스를 짜주려해. 여행이 하나의 이야기가 될 수 있도록, 여행지들을 추천해주고, 내가 주는 여행지에 대한 설명을 참고해서 추천 여행코스를 하나의 스토리 처럼 만들어줘. 즉, 추천 여행코스를 쭉 알려주고, 이 여행코스를 하나의 이야기로 만들어서 알려주는 것까지 하면 돼. 마치 이야기하는 듯한 느낌을 주도록 '해요'체로 이야기해줘.
    #
    # 여행관광지에 대한 설명은 다음과 같아: """

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
            {persona_prompt_dict[persona_type]}

여행지와 그에 대한 설명은 다음과 같아. 각각 여행지에 대한 설명에 추가로, 멋진 여행스토리를 만들어줘. 스토리는 하나의 이야기처럼 잘 만들어줘. 이때 하루에 최소 2개 이상의 여행지로 코스를 만들어줘. 다른 인사말 같은거 하지말고, 본문을 2번 반복하지도 말고, 바로 스토리에 대해서 이야기해줘. 그리고 강조할 문장이나 단어에는 볼드체 할 수 있도록 정규식으로 표시해줘. 뻔한 이야기는 하지말고, 각 관광지가 갖고있는 전설과 역사와 같이 알면 더 흥미롭게 여행할 수 있는 내용들을 포함해서 스토리를 만들어줘. 역사와 전설에 대한 이야기를 통해 여행자에게 감동을 주는 스토리로 만들어줘. 여행자가 여행지에 도착했을 때, 그곳의 분위기와 전설을 떠올리며 여행을 즐길 수 있도록 스토리를 만들어줘. 
그리고 마지막엔 어떤 관광지인지 알 수 있도록 관광지의 ID를 리스트 형태로 출력해줘. 이때 꼭, "여행스토리에 포함된 모든 관광지"의 ID를 다 포함해야해. 하나도 빠짐없이 모든 관광지의 ID를 리스트 형태로 출력해줘. 결과물은 json 파싱을 위해서, 다른 말 없이 항상 아래 예시로 들어준 json의 형태로 출력해줘. 모든 여행 코스와 스토리는 recommendation의 밸류로 전부 넣어줘. 

expected_output:
{{
    "recommendation": 
    "{persona_incontext_prompt_dict[persona_type]}",
    "ID": 
    [123203, 126444, 126444, 126444, 126444]
}}

여행지와 여행지 설명:
{travel_explain_total_text}""",
        }
    ]
    response = client.chat.completions.create(
        messages=total_message_with_prompt,
        model=MODEL,
        temperature=1.0,
        response_format={'type': "json_object"}
    )
    gpt_response = response.choices[0].message.content
    return gpt_response

@router.post("/recommend_travel")
async def recommend_travel(request: RecommendTravelRequest):
    try:
        # Location 데이터 정의
        locations = {
            # "서귀포시": {"위도": 33.2531, "경도": 126.5595},
            # "제주국제공항": {"위도": 33.5104, "경도": 126.4914},
            # "제주시": {"위도": 33.4996, "경도": 126.5312},
            # "성산일출봉": {"위도": 33.4580, "경도": 126.9411},
            # "한라산": {"위도": 33.3625, "경도": 126.5339},
            # "협재해수욕장": {"위도": 33.3948, "경도": 126.2396},
            # "중문관광단지": {"위도": 33.2500, "경도": 126.4100},
            # "우도": {"위도": 33.5020, "경도": 126.9548},
            # "섭지코지": {"위도": 33.4247, "경도": 126.9242},
            # "천지연폭포": {"위도": 33.2452, "경도": 126.5655},
            # "함덕해수욕장": {"위도": 33.5434, "경도": 126.6728},
            # "애월": {"위도": 33.4658, "경도": 126.3272}
            "제주도 서쪽": {"위도": 33.37, "경도": 126.28},
            "제주도 남쪽": {"위도": 33.27, "경도": 126.54},
            "제주도 북쪽": {"위도": 33.48, "경도": 126.55},
            "제주도 동쪽": {"위도": 33.45, "경도": 126.87},
            "한라산": {"위도": 33.36, "경도": 126.52},
            "우도": {"위도": 33.50, "경도": 126.95},
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

        filtered_df, distance = find_locations_within_k(df, request.traveltheme, 'mapx', 'mapy', target_x, target_y, 50, 10)
        if filtered_df is None or filtered_df.empty:
            raise HTTPException(status_code=404, detail="No travel spots found")

        result = recommend_travel_spots(request.persona, age, gender, request.season, request.duration, request.travelmate, filtered_df, "gpt-4o", CLIENT)
        print(result)
        # GPT의 응답에서 유효한 JSON 추출
        # try:
        #     # GPT 응답에서 JSON 부분만 추출 (코드 블록 내 JSON을 예상)
        #     start = result.find('{')
        #     end = result.rfind('}') + 1
        #     json_str = result[start:end]
        #
        #     # JSON 형식 검증
        #     response_json = json.loads(json_str)
        # except json.JSONDecodeError as json_err:
        #     print(f"JSON Decode Error: {json_err}")
        #     print(f"GPT Response: {result}")
        #     raise HTTPException(status_code=500, detail="Invalid JSON format received from GPT.")

        response_json = json.loads(result.replace("'", '"').replace("```", '').replace('json', ''))
        response = response_json.get('recommendation')
        ids = response_json.get('ID')

        if not isinstance(ids, list):
            raise HTTPException(status_code=500, detail="Invalid ID format received from GPT.")

        output_travel_df = filtered_df[filtered_df['contentsid'].isin(ids)][['contentsid','title','address','firstimage']]

        # 좋아요 상태를 가져오는 쿼리
        like_query = """
                       SELECT contentId
                       FROM likes
                       WHERE userId = %s AND contentId IN %s
                       """

        # IN 연산자를 사용하기 위해 튜플 형태로 변환
        content_ids_tuple = tuple(ids)
        if len(content_ids_tuple) == 1:
            content_ids_tuple += (None,)  # 단일 요소 튜플일 경우 콤마 추가

        # 좋아요 상태를 가져옴
        df_likes = pd.read_sql(like_query, connection, params=(request.userId, content_ids_tuple))

        # 좋아요 상태를 표시하기 위한 컬럼 추가
        output_travel_df['is_liked'] = output_travel_df['contentsid'].isin(df_likes['contentId'])
        output_travel_df = output_travel_df.rename(columns = {'contentsid':'contentid'})
        output_travel_df['contentid'] = output_travel_df['contentid'].astype(int)


        ouput_travel_result = json.loads(output_travel_df.to_json(orient='records', force_ascii=False))

        return {"recommendation": response,
                "items": ouput_travel_result}


    except HTTPException as e:
        raise e

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        if connection:
            connection.close()
