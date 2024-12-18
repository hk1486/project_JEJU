from fastapi import FastAPI
import warnings
warnings.filterwarnings('ignore')

# 사용자 관련 라우터 임포트
from login.insert_user_info import router as user_info_router
from login.select_user_id import router as login
from onboarding.onboarding_user_info import router as receive_onboarding_info
from user.select_information import router as my_info_router
from user.update_information import router as update_info_router
from user.select_like_list import router as like_list_router

# 관광아이템 관련 라우터 임포트
from travel.call_main_page_items import router as main_layout
from travel.call_travel_item_details import router as details_layout
from travel.likes import router as like_router
from travel.main_category_items import router as category

# AIdocent 관련 라우터 임포트
from docentAI.nearby_spot_title import router as docent_nearby
from docentAI.recommend_list import router as recommend_list
from docentAI.travel_course import router as recommend_travel

# 내 코스 관련 라우터 임포트
from course.router import router as course_router
from course.create import router as create_course_router
from course.select import router as select_course_router
from course.insert import router as insert_course_router
from course.detail import router as detail_course_router
from course.update import router as update_course_info_router
from course.update_course_sequence import router as update_course_plan_router


app = FastAPI()

# 각각의 라우터를 등록
app.include_router(user_info_router, prefix="/jeju")
app.include_router(login, prefix="/jeju")
# app.include_router(culture_info_router, prefix="/jeju")

app.include_router(main_layout, prefix="/jeju")
app.include_router(details_layout, prefix="/jeju")
app.include_router(receive_onboarding_info, prefix="/jeju")

app.include_router(like_router, prefix="/jeju")
app.include_router(category, prefix="/jeju")
app.include_router(docent_nearby, prefix="/jeju")
app.include_router(recommend_list, prefix="/jeju")
app.include_router(recommend_travel, prefix="/jeju")

app.include_router(course_router, prefix="/jeju/course")
app.include_router(my_info_router, prefix="/jeju")
app.include_router(update_info_router, prefix="/jeju")
app.include_router(like_list_router, prefix="/jeju")
app.include_router(create_course_router, prefix="/jeju/course")
app.include_router(select_course_router, prefix="/jeju/course")
app.include_router(insert_course_router, prefix="/jeju/course")
app.include_router(detail_course_router, prefix="/jeju/course")
app.include_router(update_course_info_router, prefix="/jeju/course")
app.include_router(update_course_plan_router, prefix="/jeju/course")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=48000)