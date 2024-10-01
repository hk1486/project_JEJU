from typing import List, Dict, Any
import warnings
warnings.filterwarnings('ignore')

TARGET_TABLE = [
    'visit_main_fix',
    'culture_main',
    'festival_main',
    'food_main',
    'leports_main',
    'shopping_main',
    'stay_main',
]

def search(cursor: any, name: str) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []

    # 첫 번째 쿼리에서 결과 수 제한
    check_query = """
    SELECT contentsid, title, target_table
    FROM main_total_v2
    WHERE title LIKE CONCAT('%%', %s, '%%')
    LIMIT %s
    """
    cursor.execute(check_query, (name, 300))
    main = cursor.fetchall()

    for record in main:
        if len(result) >= 300:
            break
        target_table = record['target_table']
        contentsid = record['contentsid']
        title = record['title']
        if target_table == 'course_main':
            continue
        # target_table이 허용된 테이블 목록에 있는지 확인
        if target_table not in TARGET_TABLE:
            continue

        detail_query = f"""
            SELECT firstimage, address, mapx, mapy
            FROM {target_table}
            WHERE contentid = %s
        """
        cursor.execute(detail_query, (contentsid,))
        detail = cursor.fetchone()

        if detail:
            result.append({
                'contentid': contentsid,
                'title': title,
                'firstimage': detail['firstimage'],
                'address': detail['address'],
                'mapx': detail['mapx'],
                'mapy': detail['mapy']
            })

    # 두 번째 쿼리에서 결과 수 제한
    if len(result) < 300:
        for target in TARGET_TABLE:
            if len(result) >= 300:
                break
            query = f"""
                SELECT contentid, title, firstimage, address, mapx, mapy
                FROM {target}
                WHERE (summary LIKE CONCAT('%%', %s, '%%') OR tag LIKE CONCAT('%%', %s, '%%'))
                LIMIT %s
            """
            cursor.execute(query, (name, name, 300 - len(result)))
            search_result = cursor.fetchall()

            for data in search_result:
                if len(result) >= 300:
                    break
                result.append({
                    'contentid': data['contentid'],
                    'title': data['title'],
                    'firstimage': data['firstimage'],
                    'address': data['address'],
                    'mapx': data['mapx'],
                    'mapy': data['mapy']
                })

    return result
