from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import os
from sshtunnel import SSHTunnelForwarder
import pymysql

load_dotenv()

app = FastAPI()

# SSH 및 MySQL 연결 정보
SSH_HOSTNAME = os.getenv('SSH_HOSTNAME')
SSH_PORT = int(os.getenv('SSH_PORT'))
SSH_USERNAME = os.getenv('SSH_USERNAME')
SSH_KEY_FILE = os.getenv('SSH_KEY_FILE')

MYSQL_HOSTNAME = os.getenv('MYSQL_HOSTNAME')
MYSQL_PORT = int(os.getenv('MYSQL_PORT'))
MYSQL_USERNAME = os.getenv('MYSQL_USERNAME')
MYSQL_PASSWORD = os.getenv('MYSQL_PASSWORD')
MYSQL_DATABASE = os.getenv('MYSQL_DATABASE')

# Pydantic 모델 정의
class UserInfo(BaseModel):
    id: int
    nickname: str


# 데이터 삽입 엔드포인트
@app.post("/user_info/")
async def create_user_info(user_info: UserInfo):
    try:
        with SSHTunnelForwarder(
                (SSH_HOSTNAME, SSH_PORT),
                ssh_username=SSH_USERNAME,
                ssh_pkey=SSH_KEY_FILE,
                remote_bind_address=(MYSQL_HOSTNAME, MYSQL_PORT)
        ) as tunnel:
            tunnel.start()
            connection = pymysql.connect(
                host='127.0.0.1',
                port=tunnel.local_bind_port,
                user=MYSQL_USERNAME,
                password=MYSQL_PASSWORD,
                database=MYSQL_DATABASE
            )

            with connection.cursor() as cursor:
                add_user = "INSERT INTO user_info (id, nickname) VALUES (%s, %s)"
                cursor.execute(add_user, (user_info.id, user_info.nickname))
                connection.commit()

            connection.close()
            return {"message": "User info inserted successfully."}

    except pymysql.MySQLError as err:
        raise HTTPException(status_code=500, detail=str(err))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))