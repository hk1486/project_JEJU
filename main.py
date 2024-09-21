from fastapi import FastAPI

from login.insert_user_info import router as user_info_router
# from travel.call_travel_items import router as culture_info_router
from onboarding.onboarding_user_info import router as receive_onboarding_info
from login.select_user_id import router as login
from travel.call_main_page_items import router as main_layout
from travel.call_travel_item_details import router as details_layout
from travel.likes import router as like_router
from course.router import router as course_router

app = FastAPI()

# 각각의 라우터를 등록
app.include_router(user_info_router, prefix="/jeju")
app.include_router(login, prefix="/jeju")
# app.include_router(culture_info_router, prefix="/jeju")

app.include_router(main_layout, prefix="/jeju")
app.include_router(details_layout, prefix="/jeju")
app.include_router(receive_onboarding_info, prefix="/jeju")

app.include_router(like_router, prefix="/jeju")

app.include_router(course_router, prefix="/jeju/course")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=48000)