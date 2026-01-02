import sqlite3
import time
import random
from datetime import datetime, timedelta
from typing import Optional
from fastapi import FastAPI, HTTPException, status, Depends, Response, Cookie, Header
from pydantic import BaseModel
from fastapi.responses import FileResponse
from jose import JWTError, jwt
from fastapi.staticfiles import StaticFiles
from datetime import timezone
from authlib.integrations.starlette_client import OAuth
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request

app = FastAPI()
# 資料庫連線
DB_FILE = 'data.db'
conn = sqlite3.connect(DB_FILE, check_same_thread=False)
cursor = conn.cursor()

# JWT 設定
SECRET_KEY = "super-secret-key"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 7

# --- 1. 初始化資料庫 ---
cursor.execute('''
    CREATE TABLE IF NOT EXISTS customer (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        password INTEGER NOT NULL,
        level INTEGER NOT NULL
    )
''')

cursor.execute('''
    CREATE TABLE IF NOT EXISTS product (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        description TEXT,
        whosProductId INTEGER NOT NULL,
        value INTEGER NOT NULL,
        image_url TEXT NULL
    )
''')

cursor.execute('''
    CREATE TABLE IF NOT EXISTS purchase (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customerId INTEGER NOT NULL,
        productId INTEGER NOT NULL,
        time INTEGER NOT NULL,
        count INTEGER NOT NULL
    )
''')
conn.commit()

def init_data():
    cursor.execute("SELECT COUNT(*) FROM customer")
    if cursor.fetchone()[0] == 0:
        customers = [('admin', 1234, 0), ('com', 321, 1)]
        cursor.executemany('INSERT INTO customer (name, password, level) VALUES (?,?,?)', customers)
    
    cursor.execute("SELECT COUNT(*) FROM product")
    if cursor.fetchone()[0] == 0:
        products = [('瓜', "老闆這瓜保熟嗎", 1, 100,None), ('T91步槍', None, 1, 67890,None)]
        cursor.executemany('INSERT INTO product (name, description, whosProductId, value,image_url) VALUES (?,?,?,?,?)', products)
    conn.commit()

init_data()

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=60 * 24 * 365 * 100)
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(authorization: str = Header(None)):
    # 1. 檢查有沒有 Header
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未提供認證 Token")
    
    # 2. 取得 Token 字串 (去掉 "Bearer " 這七個字)
    token = authorization.split(" ")[1]
    
    try:
        # 3. 解碼 Token
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: int = payload.get("user_id")
        level: int = payload.get("level")

        if user_id is None:
            raise HTTPException(status_code=401, detail="無效的 Token")
        
        return {"user_id": user_id,"level":level}
        
    except JWTError:
        raise HTTPException(status_code=401, detail="Token 已過期或無效")
# --- 2. 資料結構 (Pydantic Models) ---

class LoginData(BaseModel):
    name: str
    password: int

class ProductCreate(BaseModel):
    name: str
    description: Optional[str] = None
    price: int
    image_url: Optional[str] = None

class PurchaseRequest(BaseModel):
    product_id: int
    count: int

# --- 3. 靜態檔案 ---
# 提醒：若無 static 資料夾，請手動建立或註解掉此行
app.mount("/static", StaticFiles(directory="static"), name="static")

# --- 4. API 路徑 (已去除重複) ---

@app.get("/")
def root():
    return FileResponse('html/index.html')

@app.get("/home")
def get_home():
    return FileResponse('html/home.html')

@app.get("/manager")
def get_manager():
    return FileResponse('html/manager.html')

@app.get("/addProduct.html")
def addProduct():
    return FileResponse('html/addProduct.html')

@app.get("/manager_user.html")
def manager_user():
    return FileResponse('html/manager_user.html')

@app.get("/purchase_record.html")
def purchase_record():
    return FileResponse('html/purchase_record.html')

@app.get("/buy.html")
def buy():
    return FileResponse('html/buy.html')

@app.get("/updateProduct.html")
def updateProduct():
    return FileResponse('html/updateProduct.html')


@app.post("/login")
def login(data: LoginData):
    try:
        cursor.execute("SELECT id, name, password, level FROM customer WHERE name = ? AND password = ?", (data.name, data.password))
        user = cursor.fetchone()
        
        if not user:
            # 帳密錯，回傳你指定的 sta: 0
            return {"sta": 0, "message": "名字或密碼錯誤"}
        
        access_token = create_access_token(data={"user_id": user[0],"level":user[3]})
        
        return {
            "level":user[3],
            "sta": 1,
            "token_access": access_token, 
            "id": user[0],
        }
    except Exception as e:
        conn.rollback()
        return {"sta": 0, "message": f"伺服器出錯: {str(e)}"}


@app.get("/getProducts")
def get_products(user_id: int = Depends(get_current_user)):
    cursor.execute("SELECT id, name, description, whosProductId, value,image_url FROM product")
    rows = cursor.fetchall()
    return {
        "status": "success",
        "data": [{"id": r[0], "name": r[1], "description": r[2], "seller_id": r[3], "price": r[4],"image_url": r[5]} for r in rows]
    }

@app.post("/buyProduct")
def buy_product(
    req: PurchaseRequest, 
    user_id: int = Depends(get_current_user) # 關鍵：這行會自動執行上面的驗證
):
    # 此時，user_id 是從 Token 裡面「解密」出來的，絕對安全！
    
    # 檢查商品是否存在
    cursor.execute("SELECT name FROM product WHERE id = ?", (req.product_id,))
    product = cursor.fetchone()
    if not product:
        raise HTTPException(status_code=404, detail="商品不存在")

    try:
        # 寫入購買紀錄
        real_user_id = user_id["user_id"]
        current_time = int(time.time())
        cursor.execute('''
            INSERT INTO purchase (customerId, productId, time, count) 
            VALUES (?, ?, ?, ?)
        ''', (real_user_id, req.product_id, current_time, req.count))
        
        conn.commit()
        
        return {
            "sta": 1,
            "message": f"購買成功：{product[0]} x {req.count}",
            "user_id": user_id  # 可以回傳確認是誰買的
        }
    except Exception as e:
        conn.rollback()
        return {"sta": 0, "message": f"資料庫寫入失敗: {str(e)}"}
    
@app.get("/getPurchaseHistory")
def get_purchase_history(user_data: dict = Depends(get_current_user)):
    user_id = user_data["user_id"]
    level = user_data["level"]

    if level == 0:
        # 管理員：抓取全部，並關聯商品價格
        cursor.execute('''
            SELECT p.id, c.name, pr.name, pr.value, p.count, p.time 
            FROM purchase p
            JOIN customer c ON p.customerId = c.id
            JOIN product pr ON p.productId = pr.id
        ''')
    else:
        # 一般會員：只抓自己的
        cursor.execute('''
            SELECT p.id, c.name, pr.name, pr.value, p.count, p.time 
            FROM purchase p
            JOIN customer c ON p.customerId = c.id
            JOIN product pr ON p.productId = pr.id
            WHERE p.customerId = ?
        ''', (user_id,))
    
    rows = cursor.fetchall()
    return {
        "level": level, # 回傳 level 方便前端判斷 UI
        "data": [
            {
                "order_id": r[0], "user_name": r[1], "product": r[2], 
                "price": r[3], "count": r[4], "time": r[5]
            } for r in rows
        ]
    }

@app.post("/addProduct")
def add_product(
    item: ProductCreate, 
    user_data: dict = Depends(get_current_user)  # 關鍵：驗證身分並取得 Token 內容
):
    # 從 Token 資料中取出 user_id
    seller_id = user_data["user_id"]
    
    #"權限不足，您不是賣家"
    if user_data.get("level") != 0:
        raise HTTPException(status_code=403, detail=user_data.get("level"))

    try:
        # 將商品資訊寫入資料庫
        cursor.execute('''
            INSERT INTO product (name, description, whosProductId, value,image_url) 
            VALUES (?, ?, ?, ?,?)
        ''', (item.name, item.description, seller_id, item.price,item.image_url))
        
        conn.commit()
        
        return {
            "sta": 1, 
            "message": f"商品 '{item.name}' 上架成功！",
            "seller_id": seller_id

        }
    except Exception as e:
        conn.rollback()
        return {"sta": 0, "message": f"上架失敗: {str(e)}"}
    

    
@app.delete("/deleteProduct/{product_id}")
def delete_product(product_id: int, user_data: dict = Depends(get_current_user)):
    # 1. 權限檢查：只有管理員可以刪除 (或者你可以改成 擁有者才能刪除)
    if user_data.get("level") != 0:
        raise HTTPException(status_code=403, detail="權限不足，無法刪除商品")

    try:
        # 2. 檢查商品是否存在
        cursor.execute("SELECT id FROM product WHERE id = ?", (product_id,))
        if not cursor.fetchone():
            return {"sta": 0, "message": "找不到該商品"}

        # 3. 執行刪除
        cursor.execute("DELETE FROM product WHERE id = ?", (product_id,))
        conn.commit()
        
        return {"sta": 1, "message": "商品已成功刪除"}
    except Exception as e:
        conn.rollback()
        return {"sta": 0, "message": f"刪除失敗: {str(e)}"}
    

class ProductUpdate(BaseModel):
    name: str
    description: Optional[str] = None
    price: int
    image_url: Optional[str] = None

@app.put("/updateProduct/{product_id}")
def update_product(product_id: int, item: ProductUpdate, user_data: dict = Depends(get_current_user)):
    # 權限檢查
    if user_data.get("level") != 0:
        raise HTTPException(status_code=403, detail="權限不足")

    try:
        cursor.execute('''
            UPDATE product 
            SET name = ?, description = ?, value = ?, image_url = ?
            WHERE id = ?
        ''', (item.name, item.description, item.price, item.image_url, product_id))
        
        if cursor.rowcount == 0:
            return {"sta": 0, "message": "找不到該商品"}
            
        conn.commit()
        return {"sta": 1, "message": "商品更新成功"}
    except Exception as e:
        conn.rollback()
        return {"sta": 0, "message": f"更新失敗: {str(e)}"}
    

# 獲取所有會員 (僅限管理員)
@app.get("/getCustomers")
def get_customers(user_data: dict = Depends(get_current_user)):
    if user_data.get("level") != 0:
        raise HTTPException(status_code=403, detail="權限不足")
    
    cursor.execute("SELECT id, name, level FROM customer")
    rows = cursor.fetchall()
    return {
        "sta": 1,
        "data": [{"id": r[0], "name": r[1], "level": r[2]} for r in rows]
    }

# 刪除會員 (僅限管理員)
@app.delete("/deleteCustomer/{user_id}")
def delete_customer(user_id: int, user_data: dict = Depends(get_current_user)):
    if user_data.get("level") != 0:
        raise HTTPException(status_code=403, detail="權限不足")
    
    # 防止管理員刪除自己
    if user_id == user_data.get("user_id"):
        return {"sta": 0, "message": "你不能刪除你自己！"}

    try:
        cursor.execute("DELETE FROM customer WHERE id = ?", (user_id,))
        conn.commit()
        return {"sta": 1, "message": "會員已刪除"}
    except Exception as e:
        return {"sta": 0, "message": str(e)}
    

class RegisterData(BaseModel):
    name: str
    password: int

@app.post("/register")
def register(data: RegisterData):
    try:
        # 1. 檢查帳號是否已存在
        cursor.execute("SELECT id FROM customer WHERE name = ?", (data.name,))
        if cursor.fetchone():
            return {"sta": 0, "message": "帳號已存在"}
        
        # 2. 寫入新帳號 (預設 level 為 1，即一般會員)
        cursor.execute(
            "INSERT INTO customer (name, password, level) VALUES (?, ?, ?)",
            (data.name, data.password, 1)
        )
        conn.commit()
        return {"sta": 1, "message": "註冊成功！"}
        
    except Exception as e:
        conn.rollback()
        return {"sta": 0, "message": f"伺服器錯誤: {str(e)}"}
    


# 1. 必須加入 SessionMiddleware 才能儲存 OAuth 狀態
app.add_middleware(SessionMiddleware, secret_key="your-session-secret")

oauth = OAuth()
oauth.register(
    name='google',
    client_id='688041078983-v70vdok09qt31jdan7ag5lpap1789pi3.apps.googleusercontent.com',
    client_secret='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',
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={
        'scope': 'openid email profile'
    }
)

# 2. 登入路由：引導使用者去 Google
@app.get("/login/google")
async def login_google(request: Request):
    redirect_uri = "http://127.0.0.1:8000/auth/google/callback"
    return await oauth.google.authorize_redirect(request, redirect_uri)

# 3. 回調路由：Google 驗證完後會跳回這裡
@app.get("/auth/google/callback")
async def auth_google(request: Request):
    token = await oauth.google.authorize_access_token(request)
    user_info = token.get('userinfo')
    
    if user_info:
        email = user_info['email']
        # 查詢或建立使用者
        cursor.execute("SELECT id, level FROM customer WHERE name = ?", (email,))
        user = cursor.fetchone()
        
        if not user:
            cursor.execute("INSERT INTO customer (name, password, level) VALUES (?, ?, ?)", (email, 0, 1))
            conn.commit()
            cursor.execute("SELECT id, level FROM customer WHERE name = ?", (email,))
            user = cursor.fetchone()

        # 生成你系統的 JWT Token
        access_token = create_access_token(data={"user_id": user[0], "level": user[1]})
        
        # 重點：跳轉回登入頁面（或首頁），並把 token 帶在網址上
        response = Response(status_code=302)
        # 這裡建議跳回到 index (登入頁)，由登入頁負責存入 sessionStorage
        response.headers["Location"] = f"/?token={access_token}" 
        return response

    return {"sta": 0, "message": "Google 驗證失敗"}