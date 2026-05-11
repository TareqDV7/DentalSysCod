import sqlite3
import sys


def main(db_path='dental_clinic.db'):
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cur.fetchall()
        print('tables:', tables)
        cur.execute('PRAGMA integrity_check;')
        print('integrity:', cur.fetchone())
    except Exception as e:
        print('ERROR:', e)
        sys.exit(2)


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('--db', default='dental_clinic.db')
    args = p.parse_args()
    main(args.db)
