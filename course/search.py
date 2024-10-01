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

def search(cursor: any, name: str, sigungucode: str) -> List[Dict[str, Any]]:
    check_query = """
    select contentsid, title, target_table from main_total_v2 where title LIKE CONCAT('%%', %s, '%%')
    """
    cursor.execute(check_query, (name))
    main = cursor.fetchall()

    result: List[Dict[str, Any]] = []
    for i in range(len(main)):
        target_table = main[i]['target_table']
        contentsid = main[i]['contentsid']
        title = main[i]['title']
        if target_table == 'course_main':
            continue;

        detail_query = f"""
            select firstimage, address, mapx, mapy from {target_table} where contentid = {contentsid} and sigungucode = %s
        """
        cursor.execute(detail_query, (sigungucode))
        detail = cursor.fetchall()

        for j in range(len(detail)):
            result.append({
                'contentid': contentsid,
                'title': title,
                'firstimage': detail[j]['firstimage'],
                'address': detail[j]['address'],
                'mapx': detail[j]['mapx'],
                'mapy': detail[j]['mapy']
            })

    
    for target in TARGET_TABLE:
        query = f"""
            select contentid, title, firstimage, address, mapx, mapy from {target} where (summary LIKE CONCAT('%%', %s, '%%') or tag LIKE CONCAT('%%', %s, '%%')) and sigungucode = %s
        """
        cursor.execute(query, (name, name, sigungucode))
        search_result = cursor.fetchall()
        
        for data in search_result:
            result.append({
                'contentid': data['contentid'],
                'title': data['title'],
                'firstimage': data['firstimage'],
                'address': data['address'],
                'mapx': data['mapx'],
                'mapy': data['mapy']
            })


    return result