def search(cursor: any, name: str):
    check_query = """
    select * from main_total_v2 where title LIKE CONCAT('%%', %s, '%%')
    """
    cursor.execute(check_query, (name))
    result = cursor.fetchall()

    return result