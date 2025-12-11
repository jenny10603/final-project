-- 0. 開啟外鍵支援 (SQLite 預設關閉)
PRAGMA foreign_keys = ON;

-- 1. 商品分類
CREATE TABLE Categories (
    category_id INTEGER PRIMARY KEY, -- 自動遞增
    category_name TEXT NOT NULL
);

-- 2. 商品資訊
CREATE TABLE Products (
    product_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    price REAL NOT NULL, -- SQLite 使用 REAL 儲存浮點數
    stock_quantity INTEGER DEFAULT 0,
    category_id INTEGER,
    FOREIGN KEY (category_id) REFERENCES Categories(category_id)
);

-- 3. 會員資料
CREATE TABLE Customers (
    customer_id INTEGER PRIMARY KEY,
    full_name TEXT NOT NULL,
    phone TEXT UNIQUE,
    points INTEGER DEFAULT 0
);

-- 4. 訂單主檔
CREATE TABLE Orders (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER,
    order_date TEXT DEFAULT CURRENT_TIMESTAMP,
    total_amount REAL,
    FOREIGN KEY (customer_id) REFERENCES Customers(customer_id)
);

-- 5. 訂單明細
CREATE TABLE OrderDetails (
    detail_id INTEGER PRIMARY KEY,
    order_id INTEGER,
    product_id INTEGER,
    quantity INTEGER NOT NULL,
    unit_price REAL NOT NULL,
    FOREIGN KEY (order_id) REFERENCES Orders(order_id),
    FOREIGN KEY (product_id) REFERENCES Products(product_id)
);

-- --- 預設測試資料 (Seed Data) ---

INSERT INTO Categories (category_name) VALUES ('生鮮'), ('飲料'), ('零食');

INSERT INTO Products (name, price, stock_quantity, category_id) VALUES 
('富士蘋果', 25.0, 100, 1),
('全脂牛奶', 60.0, 50, 2),
('洋芋片', 35.0, 200, 3);

INSERT INTO Customers (full_name, phone) VALUES 
('王小明', '0912345678'),
('李小美', '0987654321');