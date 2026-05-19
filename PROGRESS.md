# Traffic Routing Bot - Tiến Độ Dự Án

**Ngày cập nhật:** 19/05/2026  
**Trạng thái hiện tại:** Đang phát triển (Development Phase)

---

## I. Tổng Quan Dự Án

### Mô Tả Dự Án
- **Tên:** AI Traffic Routing Bot
- **Mục đích:** Một bot thông minh được cấp quyền bởi trí tuệ nhân tạo để tối ưu hóa định tuyến giao thông thông minh
- **Nền tảng chính:** FastAPI (backend API), Telegram (interface chatbot)
- **Deployment:** Dockerfile cho Hugging Face Spaces (sdk: docker trong README)
- **Khu vực focus:** Thành phố Hồ Chí Minh (HCMC)
- **Kiểu dữ liệu bản đồ:** OpenStreetMap (OSM) - dữ liệu offline
- **Database:** MongoDB (tích hợp trong bus_crawler.py, scripts/eda_time.py)

### Mục Tiêu Chính
1. Cung cấp API định tuyến giao thông thông minh (traffic routing API)
2. Tích hợp chatbot Telegram để người dùng có thể yêu cầu đường đi
3. Quản lý session người dùng và trạng thái dài hạn
4. Thu thập dữ liệu thời gian thực từ bus crawler (lịch trình bus)
5. Tối ưu hóa đường đi dựa trên dữ liệu giao thông tức thời

---

## II. Kiến Trúc Kỹ Thuật Hiện Tại

### Cấu Trúc Thư Mục
```
traffic-routing-bot/
├── app/                          # Core application code
│   ├── main.py                  # Entry point - FastAPI app với lifespan management
│   ├── api/                     # API endpoints
│   │   ├── __init__.py
│   │   └── routes.py            # HTTP routes (GET /, /health-check, POST /api/v1/routing/java)
│   ├── core/                    # Cấu hình và utilities
│   │   ├── __init__.py
│   │   ├── config.py            # Settings (TELEGRAM_BOT_TOKEN, INTERNAL_API_KEY, MONGO_URI, proxies)
│   │   ├── logger.py            # Logging setup
│   │   └── state.py             # App state management (user sessions)
│   ├── models/                  # Data models
│   │   ├── __init__.py
│   │   ├── schemas.py           # Data validation schemas
│   │   └── user_session.py      # User session model
│   └── services/                # Business logic layer
│       ├── __init__.py
│       ├── bot_adapter.py       # Telegram bot integration
│       ├── core_logic.py        # Main routing logic
│       ├── utils.py             # Response helpers
│       ├── crawler/             # Bus data crawler
│       │   ├── __init__.py
│       │   ├── bus_crawler.py   # Web crawler cho dữ liệu bus tuyến
│       │   └── scheduler.py     # Scheduler cho periodic crawling
│       └── routing/             # Routing engine
│           ├── __init__.py
│           ├── map_builder.py   # Load & manage routing graph từ offline data
│           ├── pathfinder.py    # Pathfinding algorithm
│           └── service.py       # Routing service wrapper
├── data/                         # Offline data files
│   ├── hcmc_geometry_store.feather   # Geometry data (Feather format)
│   ├── hcmc_routing_clean.osm.pbf    # Filtered OSM highway data cho HCMC
│   ├── hcmc_urban_core.osm.pbf       # Raw OSM data (urban core area)
│   ├── master_stops.json             # Bus stops master data
│   └── master_stops.json:Zone.Identifier  # Zone metadata
├── docs/                         # Documentation
│   ├── Database Schema Design.md
│   ├── SSD.md                   # System/Software Design
│   └── TECHNICAL PRD files
├── scripts/                      # Utility scripts
│   ├── build_offline_graph.py   # OSM data → Routing graph conversion
│   ├── eda_time.py              # Exploratory data analysis
├── tests/                        # Test files
│   └── test_api.py
├── requirements.txt              # Python dependencies
├── Dockerfile                    # Container configuration
├── LICENSE
└── README.md
```

### Stack Công Nghệ

**Backend:**
- **Framework Web:** FastAPI 0.136.1
- **Server ASGI:** Uvicorn (implicit through FastAPI)
- **Async Runtime:** asyncio
- **Logging:** loguru 0.7.3
- **System Metrics:** psutil 7.2.2 (RAM logging)

**Data & Maps:**
- **OSM Processing:** osmnx 2.1.0
- **Graph Processing:** networkx 3.6.1
- **Geospatial:** geopandas 1.1.3
- **Data Format:** Feather (Apache Arrow), Pickle, OSM PBF
- **Visualization:** matplotlib 3.10.9

**Telegram Bot:**
- **Bot Framework:** aiogram 3.28.2
- **Proxy Support:** aiohttp-socks 0.10.1, httpx-socks 0.11.0

**Database:**
- **MongoDB** - Tích hợp qua PyMongo (bus_crawler.py, scripts/eda_time.py)
- Connection string: MONGO_URI environment variable
- Database: `traffic_db`
- Collection: `bus_speeds` - Dữ liệu tốc độ bus từ crawler

**Deployment Platform:**
- **Hugging Face Spaces** - Docker-based deployment
- Dockerfile configured for containerization

**Validation:**
- **Pydantic:** pydantic-settings, annotated-types 0.7.0
- **Email Validation:** email-validator 2.3.0

**Async HTTP:**
- **Client Libraries:** httpx 0.28.1, aiohttp 3.11.11
- **Utilities:** aiofiles 25.1.0, aiohappyeyeballs 2.6.1

**Python Version:** 3.11.15 (yêu cầu)

---

## III. Các Tính Năng Đã Triển Khai - Chi Tiết Triển Khai

---

### 1. ✅ Core Infrastructure - FastAPI Application

**File:** `app/main.py`  
**Status:** ✅ Complete  
**Chi tiết triển khai:**

- **FastAPI App Initialization**
  - Framework: FastAPI 0.136.1
  - Project name: "Traffic Routing Bot"
  - Lifespan context manager được cấu hình để quản lý startup/shutdown lifecycle

- **Startup Sequence (Lifespan)**
  - Log: "Đang nạp Bản đồ vào RAM..."
  - Log RAM trước/sau khi nạp graph (psutil)
  - Load routing graph từ offline data file
  - Initialize app state (user sessions management)
  - Create routing service instance
  - Create BusCrawler instance
  - Start Telegram bot adapter (async task)
  - Start crawler scheduler

- **Shutdown Sequence**
  - Stop crawler scheduler
  - Cancel bot task
  - Cleanup app state
  - Delete graph từ memory

- **Router Integration**
  - Include router từ `app.api.routes`
  - All endpoints available via API prefix

**Mục đích:** Là entry point chính của ứng dụng, quản lý toàn bộ lifecycle của app

---

### 2. ✅ Configuration Management System

**File:** `app/core/config.py`  
**Status:** ✅ Complete  
**Chi tiết triển khai:**

- **Settings Class (Pydantic BaseSettings)**
  - Framework: pydantic-settings
  - Configuration source: .env file
  - Encoding: UTF-8

- **Environment Variables được hỗ trợ:**
  1. `PROJECT_NAME` (default: "Traffic Routing Bot")
  2. `TELEGRAM_BOT_TOKEN` - Telegram bot token (bắt buộc)
  3. `INTERNAL_API_KEY` - API key cho Java callback (bắt buộc)
  4. `MONGO_URI` - MongoDB connection string (bắt buộc)
  5. `VN_PROXY` - Vietnam proxy URL (optional)
  6. `US_PROXY` - US proxy URL (optional)

- **Validation:**
  - Pydantic tự động validate types
  - Missing required fields sẽ raise error
  - .env file được load tự động tại startup

**Mục đích:** Centralized configuration management, environment variable handling

---

### 3. ✅ Application State Management

**File:** `app/core/state.py`  
**Status:** ✅ Complete  
**Chi tiết triển khai:**

- **User Sessions Tracking**
  - Max size: 10,000 concurrent users
  - TTL (Time-To-Live): 300 seconds (5 minutes)
  - Auto-cleanup expired sessions

- **State Initialization (init_app_state)**
  - Called tại app startup (lifespan)
  - Create user sessions store
  - Setup cleanup mechanisms

- **State Shutdown (shutdown_app_state)**
  - Called tại app shutdown
  - Cleanup all sessions
  - Release resources

- **App State Attributes:**
  - `app.state.graph` - Routing graph (loaded in memory)
  - `app.state.user_sessions` - User session store
  - `app.state.user_session_locks` - Per-session locks
  - `app.state.routing_service` - Routing service instance
  - `app.state.crawler` - Bus crawler instance
  - `app.state.crawler_scheduler` - Scheduler instance

**Mục đích:** Quản lý shared state across requests, user session persistence

---

### 4. ✅ Logging Infrastructure

**File:** `app/core/logger.py`  
**Status:** ✅ Complete  
**Chi tiết triển khai:**

- **Logging Framework:** loguru 0.7.3
- **Setup Function:** setup_logging()
- **Configuration:**
  - Structured logging
  - Configured tại app startup
  - Used throughout application

**Mục đích:** Centralized logging setup, structured log output

---

### 5. ✅ REST API Endpoints

**File:** `app/api/routes.py`  
**Status:** ✅ Complete  
**Chi tiết triển khai:**

- **Endpoint 1: GET / (Root)**
  - Description: Welcome message
  - Response: `{"message": "Welcome to the Traffic Routing Bot API!"}`
  - Status: ✅ Complete

- **Endpoint 2: GET /health-check**
  - Description: Health status check
  - Response: `{"status": "healthy"}`
  - Status: ✅ Complete
  - Also supports HEAD method

- **Endpoint 3: HEAD /health-check**
  - Same as GET but no response body
  - Status: ✅ Complete

- **Endpoint 4: POST /api/v1/routing/java**
  - Description: Xử lý định tuyến async cho hệ thống Java
  - Request body: `JavaRoutingRequest`
  - Header: `x-internal-api-key` (bắt buộc)
  - Processing: chạy background task (BackgroundTasks) và callback về `callbackUrl`
  - Ghi log thời gian tính toán route
  - Callback header: `x-internal-api-key` (INTERNAL_API_KEY)
  - Response: HTTP 202 Accepted
  - Status: ✅ Implemented

**Request/Response Models:**
- `RoutingRequest` - Pydantic model for routing requests
- `RoutingResponse` - Standardized response object
- `JavaRoutingRequest` - Request cho Java async routing

**Mục đích:** HTTP API interface, request routing, response handling

---

### 6. ✅ Offline Maps & Routing Infrastructure

**File:** `app/services/routing/map_builder.py`  
**Status:** ✅ Complete  
**Chi tiết triển khai:**

- **Function: load_routing_graph()**
  - Load serialized graph from disk
  - Graph format: Pickle (NetworkX DiGraph)
  - Return: NetworkX graph object
  - Called during app startup
  - Loaded into `app.state.graph`

- **Data Files Used:**
  1. `data/hcmc_routing_brain.pkl` - Routing graph (primary)

- **Memory Management:**
  - Graph loaded to RAM at startup
  - Accessed across all requests
  - Deleted at app shutdown

**Mục đích:** Load & manage routing graph for pathfinding operations

---

### 7. ✅ OSM Data Processing Pipeline

**File:** `scripts/build_offline_graph.py`  
**Status:** ✅ Complete  
**Chi tiết triển khai:**

**Data Processing Steps:**
1. **Input:** `data/hcmc_routing_clean.osm.pbf` (OSM PBF đã lọc)
2. **Load + Build Graph:** pyrosm `OSM.get_network()` → `osm.to_graph()`
3. **Truncate:** Giữ lại largest connected component
4. **Project:** Project graph về UTM để tính khoảng cách chính xác
5. **Outputs:**
  - `data/hcmc_routing_brain.pkl` - Routing graph (pickle)
  - `data/hcmc_geometry_store.feather` - Geometry data (Feather format)

**Area Coverage:**
- Phụ thuộc vào dữ liệu đầu vào đã lọc trong `data/hcmc_routing_clean.osm.pbf`

**Formats:**
- OSM PBF: Protocol Buffer Format (efficient binary format)
- Pickle: Python object serialization (NetworkX compatible)
- Feather: Apache Arrow columnar format (fast I/O)

**Mục đích:** Convert OSM data to graph format, optimize for routing operations

---

### 8. ✅ Telegram Bot Integration

**File:** `app/services/bot_adapter.py`  
**Status:** ✅ Basic handlers implemented  
**Chi tiết triển khai:**

- **Bot Framework:** aiogram 3.28.2
- **BotAdapter Class:**
  - Initialize with app instance
  - Method: `start_telegram_bot(user_sessions, graph)`
  - Runs as async task in app lifespan

- **Handlers Implemented:**
  - `/start` → gửi lời chào
  - `/route` → tạo/khởi động session, yêu cầu gửi vị trí xuất phát
  - Location message → gọi `process_routing_request()`
  - Log thời gian xử lý yêu cầu định tuyến
  - Reply dạng Markdown với distance, estimated_time, URL Google Maps

- **Proxy Support:**
  - US_PROXY (AiohttpSession proxy) nếu có

**Mục đích:** Telegram bot interface cho user bắt đầu flow định tuyến

---

### 9. ✅ Bus Crawler System

**File:** `app/services/crawler/bus_crawler.py` & `app/services/crawler/scheduler.py`  
**Status:** ✅ Implemented scraping + scheduler  
**Chi tiết triển khai:**

**BusCrawler Class:**
- Producer-consumer pattern với Queue
- API 1: `/prediction/predictbystopid/{stop_id}` để lấy route/variation đang tới
- API 2: `/prediction/{route_id}/{var_id}/{stop_id}/predictnextstops/5` để tính speed
- Tính tốc độ: delta_distance / delta_time (m/s)
- Anti-ban: random sleep giữa request
- Retry: 3 lần ở producer khi timeout/lỗi HTTP

**CrawlerScheduler Class:**
- Time-based schedule (Asia/Ho_Chi_Minh):
  - 22:00-03:59: ngủ 60 phút
  - 06-08, 16-18: chạy mỗi 5 phút
  - Giờ khác: chạy mỗi 20 phút
- Gọi `run_campaign()` và `gc.collect()` sau mỗi lần crawl

**MongoDB Integration:**
- Database: `traffic_db`
- Collection: `bus_speeds`
- Insert: `insert_many(all_results)` với fields:
  - from_stop_id, next_stop_id, distance_to_next_stop, speed_ms, timestamp

**Data Source:**
- Stop list đọc từ `data/master_stops.json`

**Mục đích:** Thu thập dữ liệu tốc độ bus theo thời gian thực

---

### 10. ✅ Routing Service Layer

**File:** `app/services/routing/service.py`  
**Status:** ✅ Implemented  
**Chi tiết triển khai:**

- **RoutingService Class:**
  - `find_path()` → gọi `pathfinder.find_shortest_path()` (A* trên NetworkX)
  - Trả về path + distance_km + estimated_time_min (ước lượng tốc độ 35 km/h)
  - `generate_google_maps_url()` → tạo URL Google Maps từ path
  - `to_geojson()` → convert path sang GeoJSON LineString

- **Integration with main app:**
  - Instance `routing_service` được gắn vào `app.state.routing_service`

**Mục đích:** Service layer cho routing (pathfinding + format output)

---

### 11. ✅ Core Request Processing Logic

**File:** `app/services/core_logic.py`  
**Status:** ✅ Implemented  
**Chi tiết triển khai:**

- **Function: process_routing_request(payload, app_state)**
  - Input: `RoutingRequest` payload, `app_state` (graph, sessions, services)
  - Nếu chưa có session → trả `RoutingResponse` lỗi
  - Nếu `awaiting_start` → lưu start_lat/lng, chuyển state sang `awaiting_end`
  - Nếu `awaiting_end` → gọi `routing_service.find_path()`, tạo Google Maps URL và GeoJSON
  - Cleanup session + lock sau khi xử lý xong
  - Output: `RoutingResponse` từ `_success_response` / `_error_response` (app/services/utils.py)

**Mục đích:** State machine cho flow định tuyến qua API

---

### 12. ✅ Data Models & Schemas

**File:** `app/models/user_session.py`, `app/models/schemas.py`  
**Status:** ✅ Implemented (basic schemas)  
**Chi tiết triển khai:**

- **schemas.py**
  - `RoutingRequest`: `user_id`, `platform` (telegram/java_web), `latitude`, `longitude`
  - `RoutingResponse`: `status`, `message`, `distance_km`, `estimated_time_min`, `geojson`, `navigation_url`, `map_image_url`
  - `JavaRoutingRequest` + `Location`: payload cho `/api/v1/routing/java`

- **user_session.py**
  - `UserSession`: `session_id`, `state`, `start_lat`, `start_lng`

**Mục đích:** Data validation cho request/response và session state


---

## V. Cập Nhật Lần Cuối

- **Ngày:** 19/05/2026
- **Nội dung xác minh (dựa trên git history + code hiện tại):**
  - Thêm endpoint async `/api/v1/routing/java` + callback (INTERNAL_API_KEY)
  - Chuẩn hóa output qua `RoutingResponse` + helper `app/services/utils.py`
  - Log thời gian xử lý route (Java callback + Telegram)
  - Log RAM trước/sau khi load graph (psutil)
  - Loại bỏ `request_models.py` khỏi models (file đã bị xóa)

---

**END OF PROGRESS DOCUMENT**
