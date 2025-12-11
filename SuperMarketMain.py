import sqlite3
import os

DB_FILE = 'supermarket.db'
SQL_FILE = 'SuperMarket.sql'

def init_database():
    """讀取 SQL 檔案並初始化資料庫"""
    print(f"正在讀取 {SQL_FILE}...")
    
    # 讀取 SQL 腳本內容
    with open(SQL_FILE, 'r', encoding='utf-8') as f:
        sql_script = f.read()
    
    # 連接並執行
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.executescript(sql_script)
        print(">>> 資料庫重置與初始化成功！")

def create_order(customer_id, product_items):
    """
    建立訂單的交易函式
    product_items 格式: [(product_id, quantity), ...]
    """
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        
        # 1. 建立訂單主檔 (先設金額為 0)
        cursor.execute("INSERT INTO Orders (customer_id, total_amount) VALUES (?, 0)", (customer_id,))
        order_id = cursor.lastrowid
        
        total_price = 0
        print(f"\n--- 開始建立訂單 #{order_id} ---")

        for pid, qty in product_items:
            # 查目前單價
            cursor.execute("SELECT price, name FROM Products WHERE product_id = ?", (pid,))
            result = cursor.fetchone()
            if result:
                price, name = result
                subtotal = price * qty
                total_price += subtotal
                
                # 2. 寫入明細
                cursor.execute("INSERT INTO OrderDetails (order_id, product_id, quantity, unit_price) VALUES (?, ?, ?, ?)", 
                               (order_id, pid, qty, price))
                
                # 3. 扣庫存
                cursor.execute("UPDATE Products SET stock_quantity = stock_quantity - ? WHERE product_id = ?", (qty, pid))
                print(f"購買: {name} x {qty} (單價: {price})")

        # 4. 更新訂單總金額
        cursor.execute("UPDATE Orders SET total_amount = ? WHERE order_id = ?", (total_price, order_id))
        conn.commit()
        print(f"訂單完成，總金額: ${total_price}")

def show_inventory():
    """顯示目前庫存"""
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name, stock_quantity FROM Products")
        print("\n[目前庫存狀態]")
        for row in cursor.fetchall():
            print(f"- {row[0]}: {row[1]}")

# --- 主程式執行區 ---
if __name__ == "__main__":
    # 1. 初始化
    if os.path.exists(SQL_FILE):
        init_database()
    else:
        print(f"錯誤: 找不到 {SQL_FILE}")
        exit()

    # 2. 顯示初始庫存
    show_inventory()

    # 3. 模擬交易：王小明(ID:1) 買了 2個蘋果(ID:1) 和 1瓶牛奶(ID:2)
    cart = [
        (1, 2), # product_id=1, qty=2
        (2, 1)  # product_id=2, qty=1
    ]
    create_order(customer_id=1, product_items=cart)

    # 4. 顯示交易後庫存
    show_inventory()