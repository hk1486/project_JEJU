from fastapi import FastAPI

from login.insert_user_info import router as user_info_router
from travel.call_travel_items import router as culture_info_router

app = FastAPI()

# 각각의 라우터를 등록
app.include_router(user_info_router, prefix="/jeju")
app.include_router(culture_info_router, prefix="/jeju")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)