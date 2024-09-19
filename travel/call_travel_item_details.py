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

load_dotenv()

router = APIRouter()

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


def connect_mysql(query):
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
            # 쿼리를 실행하여 데이터를 가져오기
            df = pd.read_sql(query, connection)

    except Exception as e:
        print(str(e))

    finally:
        connection.close()

    return df

if __name__ == "__main__":

    contentid = 2786082

    query = f"""SELECT target_table 
                FROM main_total_v2 
                WHERE contentsid = {contentid}"""

    df_fix = connect_mysql(query)

    target_table = df_fix['target_table'].values[0]

    detail_info_query = f"""SELECT * 
                            FROM {target_table}
                            WHERE contentid = {contentid}"""

    df_detial = connect_mysql(detail_info_query)

    print(JSONResponse(content={'result':json.loads(df_detial.to_json(orient='records', force_ascii=False))}))