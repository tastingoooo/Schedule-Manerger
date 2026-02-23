# Schedule Manager (Streamlit + SQLite)

這是一個多人排程小工具：

- 可建立多個行程表（例如：開會、打 BOSS）
- 每個人可輸入姓名與可用時段
- 以類甘特圖方式顯示所有人的可用時間
- 行程與時段資料都儲存在 SQLite

## 啟動方式

1. 安裝套件

```bash
pip install -r requirements.txt
```

2. 啟動 Streamlit

```bash
streamlit run app.py
```

3. 開啟瀏覽器後即可操作。

## 主要功能

- 行程表 CRUD
  - 新增、編輯、刪除多個行程表
- 時段 CRUD
  - 每筆時段可新增、修改、刪除
- 視覺化
  - 使用 Plotly timeline 呈現類甘特圖

## 資料庫

- 檔案：`schedule_manager.db`（程式啟動後自動建立）
- Tables：
  - `schedules`
  - `availabilities`
