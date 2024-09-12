from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, APIRouter
import os
from sshtunnel import SSHTunnelForwarder
import pymysql

load_dotenv()

router = APIRouter()

MYSQL_HOSTNAME = os.getenv('MYSQL_HOSTNAME')
MYSQL_PORT = int(os.getenv('MYSQL_PORT'))
MYSQL_USERNAME = os.getenv('MYSQL_USERNAME')
MYSQL_PASSWORD = os.getenv('MYSQL_PASSWORD')
MYSQL_DATABASE = os.getenv('MYSQL_DATABASE')

@router.get("/travel")
async def read_travel_items():
    try:
        connection = pymysql.connect(
            host=MYSQL_HOSTNAME,
            port=MYSQL_PORT,
            user=MYSQL_USERNAME,
            password=MYSQL_PASSWORD,
            database=MYSQL_DATABASE
        )

        with connection.cursor() as cursor:
            query = """
                    SELECT title, firstimage, summary
                    FROM culture_main
                    WHERE cat3 = '박물관' AND firstimage != ''
                    """
            cursor.execute(query)
            results = cursor.fetchall()

        connection.close()

        if results:
            return [{"title": row[0], "thumbnail": row[1], "description": row[2]} for row in results]
        else:
            raise HTTPException(status_code=404, detail="No data found")

    except pymysql.MySQLError as err:
        raise HTTPException(status_code=500, detail=str(err))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))