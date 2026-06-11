---
title: AI Traffic Routing Bot
colorFrom: blue
colorTo: green
sdk: docker
pinned: false
---


# Traffic Routing Bot

An AI-powered bot for smart traffic routing and optimization.

## Prerequisites

- Python 3.11.15
- OSMnx library and dependencies
- `osmium-tool` command-line utility

## Installation

### 1. Install Python Dependencies

```bash
pip install -r requirements.txt
```

### 2. Download and Process OSM Data

#### Step 1: Download Vietnam OSM Data

Download the OpenStreetMap data file from Geofabrik:

- Visit: https://download.geofabrik.de/asia/vietnam.html
- Download `vietnam-latest.osm.pbf`
- Place it in the `data/` directory

#### Step 2: Extract HCM City Area

Extract only the Ho Chi Minh City urban area:

```bash
osmium extract -b 106.58,10.70,106.82,10.88 data/vietnam-latest.osm.pbf -o data/hcmc_urban_core.osm.pbf
```

#### Step 3: Filter Highway Data

Keep only road data (highway tags):

```bash
osmium tags-filter data/hcmc_urban_core.osm.pbf w/highway -o data/hcmc_routing_clean.osm.pbf --overwrite
```

#### Step 4: Build Offline Graph

Convert the OSM data to routing graph format (pickle and feather):

```bash
python scripts/build_offline_graph.py
```

This generates:
- `data/hcmc_routing_brain.pkl` - Routing graph
- `data/hcmc_geometry_store.feather` - Geometry data

## Project Structure

```
app/
├── main.py              # Application entry point
├── api/                 # API endpoints
├── core/                # Configuration
├── models/              # Data models
└── services/            # Business logic
    ├── routing.py       # Routing service
    └── telegram_bot.py  # Telegram bot integration
data/                    # OSM data and processed files
scripts/
└── build_offline_graph.py  # Data processing script
```

## Usage

```bash
python app/main.py
```