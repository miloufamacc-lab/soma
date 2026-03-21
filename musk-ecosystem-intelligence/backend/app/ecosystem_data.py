"""
Musk Ecosystem Intelligence - Comprehensive Knowledge Base

This module contains detailed data about:
- 60+ companies in the Musk ecosystem
- 200+ relationships between entities
- Helper functions for ecosystem analysis and visualization

Core domains covered:
- Musk-controlled companies (Tesla, SpaceX, xAI, X, Neuralink, Boring Company)
- Key suppliers and manufacturers
- Competitors across industries
- Strategic partners and customers
- Government/regulatory bodies
- Major institutional investors
"""

from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, asdict
from datetime import datetime
import difflib


@dataclass
class Company:
    """Represents a company in the Musk ecosystem."""
    id: str
    name: str
    ticker: Optional[str]
    company_type: str  # "core_musk", "supplier", "competitor", "customer", "investor", "regulatory"
    sector: str
    description: str
    founded_year: int
    headquarters: str
    website: str
    status: str  # "public", "private", "government"
    market_cap: Optional[float]  # in billions USD
    employees: Optional[int]
    ceo: str


@dataclass
class Relationship:
    """Represents a connection between two entities."""
    source_id: str
    target_id: str
    relationship_type: str
    strength: int  # 1-10 scale
    description: str
    bidirectional: bool


# ============================================================================
# COMPANIES DATABASE - 60 COMPANIES
# ============================================================================

COMPANIES: Dict[str, Dict[str, Any]] = {
    # ========== CORE MUSK COMPANIES (6) ==========
    "tesla": {
        "id": "tesla",
        "name": "Tesla, Inc.",
        "ticker": "TSLA",
        "company_type": "core_musk",
        "sector": "Automotive/Energy",
        "description": "Leading electric vehicle manufacturer and renewable energy company. Core platform for autonomous driving (FSD), battery technology, and energy storage. Musk is CEO and largest shareholder.",
        "founded_year": 2003,
        "headquarters": "Austin, Texas, USA",
        "website": "https://www.tesla.com",
        "status": "public",
        "market_cap": 820.0,
        "employees": 128000,
        "ceo": "Elon Musk"
    },
    "spacex": {
        "id": "spacex",
        "name": "Space Exploration Technologies (SpaceX)",
        "ticker": None,
        "company_type": "core_musk",
        "sector": "Aerospace/Space",
        "description": "Private aerospace manufacturer and space transportation company. Operates Falcon 9/Heavy rockets, Starship, Dragon spacecraft, and Starlink satellite constellation. Valued at ~$180B. Musk is founder and CTO.",
        "founded_year": 2002,
        "headquarters": "Hawthorne, California, USA",
        "website": "https://www.spacex.com",
        "status": "private",
        "market_cap": 180.0,
        "employees": 10000,
        "ceo": "Elon Musk"
    },
    "xai": {
        "id": "xai",
        "name": "xAI Corporation",
        "ticker": None,
        "company_type": "core_musk",
        "sector": "Artificial Intelligence",
        "description": "Advanced AI research and development company focused on AI safety and reasoning. Developing Grok chatbot and reasoning models. Direct competitor to OpenAI and Anthropic. Musk is founder and CEO.",
        "founded_year": 2023,
        "headquarters": "San Francisco, California, USA",
        "website": "https://www.xai.com",
        "status": "private",
        "market_cap": None,
        "employees": 200,
        "ceo": "Elon Musk"
    },
    "x_twitter": {
        "id": "x_twitter",
        "name": "X (formerly Twitter)",
        "ticker": None,
        "company_type": "core_musk",
        "sector": "Social Media/Technology",
        "description": "Global social media and messaging platform. Acquired by Musk in 2022 for $44B. Rebranded as 'X' in 2023. Critical platform for Musk's communication and xAI integration.",
        "founded_year": 2006,
        "headquarters": "San Francisco, California, USA",
        "website": "https://www.x.com",
        "status": "private",
        "market_cap": 19.0,
        "employees": 2500,
        "ceo": "Elon Musk"
    },
    "neuralink": {
        "id": "neuralink",
        "name": "Neuralink Corporation",
        "ticker": None,
        "company_type": "core_musk",
        "sector": "Biotechnology/Neuroscience",
        "description": "Brain-computer interface company developing implants to restore neural function and enable human-AI symbiosis. FDA approved for human trials (2023). Valued at ~$5B.",
        "founded_year": 2016,
        "headquarters": "Fremont, California, USA",
        "website": "https://www.neuralink.com",
        "status": "private",
        "market_cap": 5.0,
        "employees": 400,
        "ceo": "Neuralink Team (Musk oversight)"
    },
    "boring_company": {
        "id": "boring_company",
        "name": "The Boring Company",
        "ticker": None,
        "company_type": "core_musk",
        "sector": "Infrastructure/Tunneling",
        "description": "Tunnel construction and infrastructure company using proprietary boring machines. Operating Las Vegas Loop, developing LA/CA tunnel networks.",
        "founded_year": 2016,
        "headquarters": "Hawthorne, California, USA",
        "website": "https://www.boringcompany.com",
        "status": "private",
        "market_cap": 5.0,
        "employees": 300,
        "ceo": "Elon Musk"
    },

    # ========== KEY SUPPLIERS (15) ==========
    "nvidia": {
        "id": "nvidia",
        "name": "NVIDIA Corporation",
        "ticker": "NVDA",
        "company_type": "supplier",
        "sector": "Semiconductors",
        "description": "Leading GPU manufacturer. Critical supplier of H100/H200 chips for Tesla FSD training, xAI model development, and SpaceX applications.",
        "founded_year": 1993,
        "headquarters": "Santa Clara, California, USA",
        "website": "https://www.nvidia.com",
        "status": "public",
        "market_cap": 3500.0,
        "employees": 28000,
        "ceo": "Jensen Huang"
    },
    "panasonic": {
        "id": "panasonic",
        "name": "Panasonic Holdings Corporation",
        "ticker": "PCRFY",
        "company_type": "supplier",
        "sector": "Electronics/Batteries",
        "description": "Major battery cell supplier for Tesla. Long-standing partnership since Model S. Supplies cylindrical battery cells (18650, 21700) for Tesla vehicles.",
        "founded_year": 1918,
        "headquarters": "Osaka, Japan",
        "website": "https://www.panasonic.com",
        "status": "public",
        "market_cap": 22.0,
        "employees": 250000,
        "ceo": "Yuki Kusumi"
    },
    "catl": {
        "id": "catl",
        "name": "Contemporary Amperex Technology Co., Ltd (CATL)",
        "ticker": None,
        "company_type": "supplier",
        "sector": "Batteries",
        "description": "World's largest battery manufacturer. Major Tesla battery supplier (LFP cells). Also supplies BYD, BMW, VW. ~40% of global EV battery market.",
        "founded_year": 2011,
        "headquarters": "Ningde, Fujian, China",
        "website": "https://www.catl.com",
        "status": "public",
        "market_cap": 85.0,
        "employees": 40000,
        "ceo": "Zeng Yuqun"
    },
    "lg_energy": {
        "id": "lg_energy",
        "name": "LG Energy Solution Ltd.",
        "ticker": "LGES",
        "company_type": "supplier",
        "sector": "Batteries",
        "description": "Major battery cell supplier for Tesla and global EV manufacturers. Supplies pouch cells for Model Y, Model 3. Second-largest EV battery maker globally.",
        "founded_year": 2020,
        "headquarters": "Seoul, South Korea",
        "website": "https://www.lges.com",
        "status": "public",
        "market_cap": 15.0,
        "employees": 25000,
        "ceo": "Kwon Oh-hyun"
    },
    "samsung_sdi": {
        "id": "samsung_sdi",
        "name": "Samsung SDI Co., Ltd.",
        "ticker": None,
        "company_type": "supplier",
        "sector": "Batteries/Electronics",
        "description": "Battery and electronics supplier. Supplies battery cells and power management systems to Tesla and other EV manufacturers.",
        "founded_year": 1970,
        "headquarters": "Seoul, South Korea",
        "website": "https://www.samsungsdi.com",
        "status": "public",
        "market_cap": 8.0,
        "employees": 30000,
        "ceo": "Yoon Ho-jung"
    },
    "tsmc": {
        "id": "tsmc",
        "name": "Taiwan Semiconductor Manufacturing Company (TSMC)",
        "ticker": "TSM",
        "company_type": "supplier",
        "sector": "Semiconductors",
        "description": "World's largest semiconductor foundry. Manufactures chips for Tesla's infotainment systems, SpaceX avionics, and other Musk ecosystem companies. 5nm to 3nm capabilities.",
        "founded_year": 1987,
        "headquarters": "Hsinchu, Taiwan",
        "website": "https://www.tsmc.com",
        "status": "public",
        "market_cap": 800.0,
        "employees": 73000,
        "ceo": "Wei-Ming Chen"
    },
    "sk_hynix": {
        "id": "sk_hynix",
        "name": "SK Hynix Inc.",
        "ticker": None,
        "company_type": "supplier",
        "sector": "Memory Chips",
        "description": "Major DRAM and NAND flash memory supplier. Components used in Tesla vehicle electronics, SpaceX avionics, and xAI infrastructure.",
        "founded_year": 1983,
        "headquarters": "Icheon, South Korea",
        "website": "https://www.skhynix.com",
        "status": "public",
        "market_cap": 25.0,
        "employees": 30000,
        "ceo": "Lee Seung-hwan"
    },
    "qualcomm": {
        "id": "qualcomm",
        "name": "Qualcomm Incorporated",
        "ticker": "QCOM",
        "company_type": "supplier",
        "sector": "Semiconductors",
        "description": "Leading wireless and infotainment chip supplier. Supplies Snapdragon processors for Tesla vehicle infotainment systems and connectivity modules.",
        "founded_year": 1985,
        "headquarters": "San Diego, California, USA",
        "website": "https://www.qualcomm.com",
        "status": "public",
        "market_cap": 200.0,
        "employees": 45000,
        "ceo": "Cristiano Amon"
    },
    "bosch": {
        "id": "bosch",
        "name": "Robert Bosch GmbH",
        "ticker": None,
        "company_type": "supplier",
        "sector": "Automotive Components",
        "description": "Global automotive parts supplier. Provides sensors, control systems, and other components for Tesla vehicles and other manufacturers.",
        "founded_year": 1886,
        "headquarters": "Stuttgart, Germany",
        "website": "https://www.bosch.com",
        "status": "private",
        "market_cap": None,
        "employees": 400000,
        "ceo": "Stefan Hartung"
    },
    "intel": {
        "id": "intel",
        "name": "Intel Corporation",
        "ticker": "INTC",
        "company_type": "supplier",
        "sector": "Semiconductors",
        "description": "Legacy semiconductor manufacturer. Limited presence in Tesla/SpaceX due to process node disadvantage. Some legacy automotive applications.",
        "founded_year": 1968,
        "headquarters": "Santa Clara, California, USA",
        "website": "https://www.intel.com",
        "status": "public",
        "market_cap": 200.0,
        "employees": 110000,
        "ceo": "Pat Gelsinger"
    },
    "infineon": {
        "id": "infineon",
        "name": "Infineon Technologies AG",
        "ticker": "IFNNY",
        "company_type": "supplier",
        "sector": "Power Semiconductors",
        "description": "Power semiconductor supplier for EV drivetrains and power management. Supplies IGBT and SiC chips for Tesla and SpaceX applications.",
        "founded_year": 1999,
        "headquarters": "Munich, Germany",
        "website": "https://www.infineon.com",
        "status": "public",
        "market_cap": 42.0,
        "employees": 57000,
        "ceo": "Joerg Braukmann"
    },
    "amphenol": {
        "id": "amphenol",
        "name": "Amphenol Corporation",
        "ticker": "APH",
        "company_type": "supplier",
        "sector": "Connectors/Electronics",
        "description": "Leading connector and cable supplier. Supplies high-reliability connectors for Tesla, SpaceX Starlink, and other applications requiring robust electronics.",
        "founded_year": 1935,
        "headquarters": "Wallingford, Connecticut, USA",
        "website": "https://www.amphenol.com",
        "status": "public",
        "market_cap": 38.0,
        "employees": 75000,
        "ceo": "Craig Lampo"
    },
    "foxconn": {
        "id": "foxconn",
        "name": "Foxconn Technology Group",
        "ticker": None,
        "company_type": "supplier",
        "sector": "Manufacturing/Assembly",
        "description": "World's largest electronics manufacturer by revenue. Manufacturing partner for Tesla components and various electronics assembly.",
        "founded_year": 1974,
        "headquarters": "Taipei, Taiwan",
        "website": "https://www.foxconn.com",
        "status": "public",
        "market_cap": 50.0,
        "employees": 800000,
        "ceo": "Young Liu"
    },
    "corning": {
        "id": "corning",
        "name": "Corning Incorporated",
        "ticker": "GLW",
        "company_type": "supplier",
        "sector": "Materials/Glass",
        "description": "Advanced materials company. Supplies glass and ceramics for Tesla vehicles, optical components for SpaceX, and specialty materials.",
        "founded_year": 1851,
        "headquarters": "Corning, New York, USA",
        "website": "https://www.corning.com",
        "status": "public",
        "market_cap": 30.0,
        "employees": 45000,
        "ceo": "Wendell Weeks"
    },
    "3m": {
        "id": "3m",
        "name": "3M Company",
        "ticker": "MMM",
        "company_type": "supplier",
        "sector": "Industrial Materials",
        "description": "Diversified manufacturing company. Supplies adhesives, tapes, thermal management materials, and other components to Tesla and SpaceX.",
        "founded_year": 1902,
        "headquarters": "Saint Paul, Minnesota, USA",
        "website": "https://www.3m.com",
        "status": "public",
        "market_cap": 100.0,
        "employees": 97000,
        "ceo": "Mike Roman"
    },

    # ========== COMPETITORS (12) ==========
    "byd": {
        "id": "byd",
        "name": "BYD Company Limited",
        "ticker": "BYDDY",
        "company_type": "competitor",
        "sector": "Automotive/Energy",
        "description": "Chinese EV and battery manufacturer. Now leads global EV sales (2023+). Direct competitor to Tesla in EVs and batteries. Integrated manufacturer with CATL battery supply.",
        "founded_year": 1995,
        "headquarters": "Shenzhen, China",
        "website": "https://www.byd.com",
        "status": "public",
        "market_cap": 180.0,
        "employees": 600000,
        "ceo": "Wang Chuanfu"
    },
    "nio": {
        "id": "nio",
        "name": "NIO Inc.",
        "ticker": "NIO",
        "company_type": "competitor",
        "sector": "Automotive",
        "description": "Chinese EV maker focused on premium segment. Battery-as-a-service model. Competes with Tesla in Chinese market with advanced autonomous driving features.",
        "founded_year": 2014,
        "headquarters": "Shanghai, China",
        "website": "https://www.nio.com",
        "status": "public",
        "market_cap": 8.0,
        "employees": 12000,
        "ceo": "William Li"
    },
    "rivian": {
        "id": "rivian",
        "name": "Rivian Automotive, Inc.",
        "ticker": "RIVN",
        "company_type": "competitor",
        "sector": "Automotive",
        "description": "American EV startup focused on adventure vehicles (R1T, R1S). Competes with Tesla in premium EV segment. Developing autonomous driving capabilities.",
        "founded_year": 2009,
        "headquarters": "Chicago, Illinois, USA",
        "website": "https://www.rivian.com",
        "status": "public",
        "market_cap": 20.0,
        "employees": 12000,
        "ceo": "RJ Scaringe"
    },
    "lucid": {
        "id": "lucid",
        "name": "Lucid Group, Inc.",
        "ticker": "LCID",
        "company_type": "competitor",
        "sector": "Automotive",
        "description": "American luxury EV manufacturer. Produces Lucid Air sedan. Competes directly with Tesla in luxury segment. Technology licensing from Aston Martin.",
        "founded_year": 2007,
        "headquarters": "Phoenix, Arizona, USA",
        "website": "https://www.lucidmotors.com",
        "status": "public",
        "market_cap": 8.0,
        "employees": 4000,
        "ceo": "Peter Rawlinson"
    },
    "blue_origin": {
        "id": "blue_origin",
        "name": "Blue Origin",
        "ticker": None,
        "company_type": "competitor",
        "sector": "Aerospace/Space",
        "description": "Private aerospace company founded by Jeff Bezos. Develops New Shepard suborbital, New Glenn orbital rockets, and Blue Moon lunar lander. Direct competitor to SpaceX.",
        "founded_year": 2000,
        "headquarters": "Seattle, Washington, USA",
        "website": "https://www.blueorigin.com",
        "status": "private",
        "market_cap": 18.0,
        "employees": 3500,
        "ceo": "Kelly Ortberg"
    },
    "ula": {
        "id": "ula",
        "name": "United Launch Alliance",
        "ticker": None,
        "company_type": "competitor",
        "sector": "Aerospace/Space",
        "description": "Joint venture of Boeing and Lockheed Martin for national security launches. Competitor to SpaceX for U.S. government and military contracts.",
        "founded_year": 2006,
        "headquarters": "Centennial, Colorado, USA",
        "website": "https://www.ulalaunch.com",
        "status": "private",
        "market_cap": None,
        "employees": 2000,
        "ceo": "Tory Bruno"
    },
    "openai": {
        "id": "openai",
        "name": "OpenAI",
        "ticker": None,
        "company_type": "competitor",
        "sector": "Artificial Intelligence",
        "description": "Leading AI research lab and product company. Develops GPT models and ChatGPT. Primary competitor to xAI. Musk co-founded but left board in 2018.",
        "founded_year": 2015,
        "headquarters": "San Francisco, California, USA",
        "website": "https://www.openai.com",
        "status": "private",
        "market_cap": 80.0,
        "employees": 900,
        "ceo": "Sam Altman"
    },
    "anthropic": {
        "id": "anthropic",
        "name": "Anthropic",
        "ticker": None,
        "company_type": "competitor",
        "sector": "Artificial Intelligence",
        "description": "AI safety company developing Claude models. Focused on safe, aligned AI systems. Major competitor to xAI and OpenAI.",
        "founded_year": 2021,
        "headquarters": "San Francisco, California, USA",
        "website": "https://www.anthropic.com",
        "status": "private",
        "market_cap": 20.0,
        "employees": 500,
        "ceo": "Dario Amodei"
    },
    "meta": {
        "id": "meta",
        "name": "Meta Platforms, Inc.",
        "ticker": "META",
        "company_type": "competitor",
        "sector": "Technology/Social Media",
        "description": "Social media and metaverse company (Facebook, Instagram, WhatsApp). Competes with X/Twitter. Developing LLaMA AI models. Active in autonomous driving research.",
        "founded_year": 2004,
        "headquarters": "Menlo Park, California, USA",
        "website": "https://www.meta.com",
        "status": "public",
        "market_cap": 1200.0,
        "employees": 70000,
        "ceo": "Mark Zuckerberg"
    },
    "google": {
        "id": "google",
        "name": "Alphabet Inc. (Google)",
        "ticker": "GOOGL",
        "company_type": "competitor",
        "sector": "Technology/AI",
        "description": "Tech giant with Waymo autonomous driving division, Gemini AI models, search. Competes with Tesla FSD, xAI, and X/Google News ecosystem.",
        "founded_year": 1998,
        "headquarters": "Mountain View, California, USA",
        "website": "https://www.google.com",
        "status": "public",
        "market_cap": 2200.0,
        "employees": 190000,
        "ceo": "Sundar Pichai"
    },
    "apple": {
        "id": "apple",
        "name": "Apple Inc.",
        "ticker": "AAPL",
        "company_type": "competitor",
        "sector": "Technology/Automotive",
        "description": "Tech giant exploring EV development (Project Titan). Competes with Tesla on infotainment, autonomous tech, and premium vehicles. Controls iOS ecosystem.",
        "founded_year": 1976,
        "headquarters": "Cupertino, California, USA",
        "website": "https://www.apple.com",
        "status": "public",
        "market_cap": 3000.0,
        "employees": 164000,
        "ceo": "Tim Cook"
    },
    "amazon": {
        "id": "amazon",
        "name": "Amazon.com, Inc.",
        "ticker": "AMZN",
        "company_type": "competitor",
        "sector": "Technology/Logistics",
        "description": "E-commerce and cloud giant. Competes with SpaceX via Kuiper satellite internet. AWS powers much of the cloud infrastructure for AI companies.",
        "founded_year": 1994,
        "headquarters": "Seattle, Washington, USA",
        "website": "https://www.amazon.com",
        "status": "public",
        "market_cap": 1900.0,
        "employees": 1500000,
        "ceo": "Andy Jassy"
    },

    # ========== CUSTOMERS/PARTNERS (8) ==========
    "nasa": {
        "id": "nasa",
        "name": "National Aeronautics and Space Administration (NASA)",
        "ticker": None,
        "company_type": "customer",
        "sector": "Government/Space",
        "description": "U.S. space agency. Major customer of SpaceX for cargo resupply and crewed missions to ISS. Artemis partner for lunar missions. Research collaborations with Tesla.",
        "founded_year": 1958,
        "headquarters": "Washington, D.C., USA",
        "website": "https://www.nasa.gov",
        "status": "government",
        "market_cap": None,
        "employees": 18000,
        "ceo": "Bill Nelson (Administrator)"
    },
    "us_dod": {
        "id": "us_dod",
        "name": "United States Department of Defense (DoD)",
        "ticker": None,
        "company_type": "customer",
        "sector": "Government/Defense",
        "description": "U.S. military establishment. Major customer of SpaceX (Starshield, national security launches). Tesla involved in defense tech research. Regulatory authority.",
        "founded_year": 1947,
        "headquarters": "Washington, D.C., USA",
        "website": "https://www.defense.gov",
        "status": "government",
        "market_cap": None,
        "employees": 2800000,
        "ceo": "Lloyd Austin (Secretary)"
    },
    "hertz": {
        "id": "hertz",
        "name": "Hertz Global Holdings, Inc.",
        "ticker": "HTZ",
        "company_type": "customer",
        "sector": "Transportation/Rental",
        "description": "Car rental company with major Tesla fleet commitments. Large customer for Tesla vehicles, part of EV adoption strategy.",
        "founded_year": 1918,
        "headquarters": "Estero, Florida, USA",
        "website": "https://www.hertz.com",
        "status": "public",
        "market_cap": 2.0,
        "employees": 23000,
        "ceo": "Gil West"
    },
    "uber": {
        "id": "uber",
        "name": "Uber Technologies, Inc.",
        "ticker": "UBER",
        "company_type": "customer",
        "sector": "Transportation/Technology",
        "description": "Ride-sharing and logistics platform. Strategic partner for autonomous vehicle deployment. Potential customer for Tesla robotaxi and autonomous fleet.",
        "founded_year": 2009,
        "headquarters": "San Francisco, California, USA",
        "website": "https://www.uber.com",
        "status": "public",
        "market_cap": 110.0,
        "employees": 77000,
        "ceo": "Dara Khosrowshahi"
    },
    "delta": {
        "id": "delta",
        "name": "Delta Air Lines, Inc.",
        "ticker": "DAL",
        "company_type": "customer",
        "sector": "Aviation",
        "description": "Major U.S. airline. Starlink customer for in-flight connectivity and aviation applications.",
        "founded_year": 1925,
        "headquarters": "Atlanta, Georgia, USA",
        "website": "https://www.delta.com",
        "status": "public",
        "market_cap": 35.0,
        "employees": 90000,
        "ceo": "Ed Bastian"
    },
    "tmobile": {
        "id": "tmobile",
        "name": "T-Mobile US, Inc.",
        "ticker": "TMUS",
        "company_type": "customer",
        "sector": "Telecommunications",
        "description": "Major U.S. wireless carrier. Strategic partner with SpaceX for Starlink direct-to-cell service. Integrating satellite messaging into cellular service.",
        "founded_year": 1994,
        "headquarters": "Bellevue, Washington, USA",
        "website": "https://www.t-mobile.com",
        "status": "public",
        "market_cap": 180.0,
        "employees": 75000,
        "ceo": "Mike Sievert"
    },
    "saudi_aramco": {
        "id": "saudi_aramco",
        "name": "Saudi Aramco",
        "ticker": None,
        "company_type": "customer",
        "sector": "Energy",
        "description": "Saudi Arabian oil and energy company. Energy sector partner. Discussions on sustainable energy transition and Tesla technology.",
        "founded_year": 1933,
        "headquarters": "Dhahran, Saudi Arabia",
        "website": "https://www.saudiaramco.com",
        "status": "public",
        "market_cap": 2000.0,
        "employees": 80000,
        "ceo": "Amin H. Nasser"
    },
    "toyota": {
        "id": "toyota",
        "name": "Toyota Motor Corporation",
        "ticker": "TM",
        "company_type": "customer",
        "sector": "Automotive",
        "description": "Global automotive manufacturer. Occasional technology licensing and strategic discussions with Tesla on autonomous driving and EV development.",
        "founded_year": 1937,
        "headquarters": "Toyota, Japan",
        "website": "https://www.toyota.com",
        "status": "public",
        "market_cap": 300.0,
        "employees": 370000,
        "ceo": "Koji Sato"
    },

    # ========== GOVERNMENT/REGULATORY (8) ==========
    "faa": {
        "id": "faa",
        "name": "Federal Aviation Administration (FAA)",
        "ticker": None,
        "company_type": "regulatory",
        "sector": "Government/Regulatory",
        "description": "U.S. aviation regulator. Oversees SpaceX launch licenses, Starship testing, and reusable rocket certifications.",
        "founded_year": 1958,
        "headquarters": "Washington, D.C., USA",
        "website": "https://www.faa.gov",
        "status": "government",
        "market_cap": None,
        "employees": 47000,
        "ceo": "Mike Whitaker (Administrator)"
    },
    "nhtsa": {
        "id": "nhtsa",
        "name": "National Highway Traffic Safety Administration (NHTSA)",
        "ticker": None,
        "company_type": "regulatory",
        "sector": "Government/Regulatory",
        "description": "U.S. vehicle safety regulator. Oversees Tesla vehicle safety testing, Full Self-Driving oversight, and recall investigations.",
        "founded_year": 1970,
        "headquarters": "Washington, D.C., USA",
        "website": "https://www.nhtsa.gov",
        "status": "government",
        "market_cap": None,
        "employees": 620,
        "ceo": "Steven Cliff (Administrator)"
    },
    "sec_gov": {
        "id": "sec_gov",
        "name": "U.S. Securities and Exchange Commission (SEC)",
        "ticker": None,
        "company_type": "regulatory",
        "sector": "Government/Regulatory",
        "description": "U.S. securities regulator. Oversees Tesla public disclosures, Musk conduct investigations, and disclosure requirements for public companies.",
        "founded_year": 1934,
        "headquarters": "Washington, D.C., USA",
        "website": "https://www.sec.gov",
        "status": "government",
        "market_cap": None,
        "employees": 4500,
        "ceo": "Gary Gensler (Chair)"
    },
    "epa": {
        "id": "epa",
        "name": "U.S. Environmental Protection Agency (EPA)",
        "ticker": None,
        "company_type": "regulatory",
        "sector": "Government/Regulatory",
        "description": "U.S. environmental regulator. Oversees Tesla emission credits, Starlink environmental impact, and battery recycling standards.",
        "founded_year": 1970,
        "headquarters": "Washington, D.C., USA",
        "website": "https://www.epa.gov",
        "status": "government",
        "market_cap": None,
        "employees": 13000,
        "ceo": "Michael Regan (Administrator)"
    },
    "fcc": {
        "id": "fcc",
        "name": "Federal Communications Commission (FCC)",
        "ticker": None,
        "company_type": "regulatory",
        "sector": "Government/Regulatory",
        "description": "U.S. communications regulator. Oversees Starlink satellite frequency licenses, X/Twitter broadcast rules, and spectrum allocation.",
        "founded_year": 1934,
        "headquarters": "Washington, D.C., USA",
        "website": "https://www.fcc.gov",
        "status": "government",
        "market_cap": None,
        "employees": 1900,
        "ceo": "Jessica Rosenworcel (Chair)"
    },
    "california_dmv": {
        "id": "california_dmv",
        "name": "California Department of Motor Vehicles (DMV)",
        "ticker": None,
        "company_type": "regulatory",
        "sector": "Government/Regulatory",
        "description": "California vehicle regulator. Issues autonomous vehicle testing and deployment permits. Critical for Tesla FSD development and testing.",
        "founded_year": 1905,
        "headquarters": "Sacramento, California, USA",
        "website": "https://www.dmv.ca.gov",
        "status": "government",
        "market_cap": None,
        "employees": 2500,
        "ceo": "Steve Gordon (Director)"
    },
    "us_congress": {
        "id": "us_congress",
        "name": "United States Congress",
        "ticker": None,
        "company_type": "regulatory",
        "sector": "Government/Legislative",
        "description": "U.S. legislative body. Sets regulations for space, EV incentives, AI governance, and tech antitrust. Direct impact on Musk ecosystem policy.",
        "founded_year": 1789,
        "headquarters": "Washington, D.C., USA",
        "website": "https://www.congress.gov",
        "status": "government",
        "market_cap": None,
        "employees": 30000,
        "ceo": "N/A (Legislative)"
    },
    "doge": {
        "id": "doge",
        "name": "Department of Government Efficiency (DOGE)",
        "ticker": None,
        "company_type": "regulatory",
        "sector": "Government/Advisory",
        "description": "Musk advisory council for government efficiency. Formed post-2024 election. Focused on reducing government spending and regulatory burden.",
        "founded_year": 2024,
        "headquarters": "Washington, D.C., USA",
        "website": "https://www.doge.gov",
        "status": "government",
        "market_cap": None,
        "employees": 20,
        "ceo": "Elon Musk (Co-Head)"
    },

    # ========== KEY INVESTORS (5) ==========
    "blackrock": {
        "id": "blackrock",
        "name": "BlackRock, Inc.",
        "ticker": "BLK",
        "company_type": "investor",
        "sector": "Asset Management",
        "description": "World's largest asset manager ($10T+ AUM). Major institutional investor in Tesla and SpaceX vehicles through index funds and active management.",
        "founded_year": 1988,
        "headquarters": "New York, New York, USA",
        "website": "https://www.blackrock.com",
        "status": "public",
        "market_cap": 150.0,
        "employees": 20000,
        "ceo": "Laurence Fink"
    },
    "vanguard": {
        "id": "vanguard",
        "name": "The Vanguard Group",
        "ticker": None,
        "company_type": "investor",
        "sector": "Asset Management",
        "description": "Second-largest asset manager ($8T+ AUM). Major shareholder in Tesla and other Musk ecosystem companies. Large index fund investor.",
        "founded_year": 1975,
        "headquarters": "Malvern, Pennsylvania, USA",
        "website": "https://www.vanguard.com",
        "status": "private",
        "market_cap": None,
        "employees": 18000,
        "ceo": "Tim Buckley"
    },
    "fidelity": {
        "id": "fidelity",
        "name": "Fidelity Investments",
        "ticker": None,
        "company_type": "investor",
        "sector": "Asset Management",
        "description": "Major asset manager and mutual fund provider. Significant investor in Tesla, SpaceX (secondary market), and Musk ecosystem companies.",
        "founded_year": 1946,
        "headquarters": "Boston, Massachusetts, USA",
        "website": "https://www.fidelity.com",
        "status": "private",
        "market_cap": None,
        "employees": 40000,
        "ceo": "Abigail Johnson"
    },
    "saudi_pif": {
        "id": "saudi_pif",
        "name": "Saudi Public Investment Fund (PIF)",
        "ticker": None,
        "company_type": "investor",
        "sector": "Sovereign Wealth",
        "description": "Saudi Arabia's sovereign wealth fund ($925B+ assets). Investor in X/Twitter and discussions on technology partnerships.",
        "founded_year": 2008,
        "headquarters": "Riyadh, Saudi Arabia",
        "website": "https://www.pif.gov.sa",
        "status": "government",
        "market_cap": None,
        "employees": 3000,
        "ceo": "Mohammed Al-Jadaan (Governor)"
    },
    "ark_invest": {
        "id": "ark_invest",
        "name": "ARK Investment Management",
        "ticker": "ARKK",
        "company_type": "investor",
        "sector": "Asset Management",
        "description": "Active investment manager founded by Cathie Wood. Bullish on Tesla and innovation. Major Tesla shareholder through ARK ETFs.",
        "founded_year": 2011,
        "headquarters": "New York, New York, USA",
        "website": "https://ark-invest.com",
        "status": "public",
        "market_cap": 8.0,
        "employees": 150,
        "ceo": "Cathie Wood"
    },

    # ========== ADDITIONAL COMPANIES (6+) ==========
    "samsung": {
        "id": "samsung",
        "name": "Samsung Electronics Co., Ltd.",
        "ticker": None,
        "company_type": "competitor",
        "sector": "Electronics/Semiconductors",
        "description": "South Korean electronics giant. Competes with Apple in smartphones, provides displays for Tesla, semiconductors for various applications.",
        "founded_year": 1938,
        "headquarters": "Seoul, South Korea",
        "website": "https://www.samsung.com",
        "status": "public",
        "market_cap": 300.0,
        "employees": 270000,
        "ceo": "Lee Jae-yong"
    },
    "bmw": {
        "id": "bmw",
        "name": "Bayerische Motoren Werke (BMW)",
        "ticker": None,
        "company_type": "competitor",
        "sector": "Automotive",
        "description": "German luxury automaker transitioning to EVs. Competes with Tesla in premium segment. Partners with Google on Android Automotive.",
        "founded_year": 1916,
        "headquarters": "Munich, Germany",
        "website": "https://www.bmwgroup.com",
        "status": "public",
        "market_cap": 60.0,
        "employees": 150000,
        "ceo": "Oliver Zipse"
    },
    "volkswagen": {
        "id": "volkswagen",
        "name": "Volkswagen Group",
        "ticker": None,
        "company_type": "competitor",
        "sector": "Automotive",
        "description": "German automotive conglomerate. Major EV transition through ID.family. Competes globally with Tesla on scale and technology.",
        "founded_year": 1937,
        "headquarters": "Wolfsburg, Germany",
        "website": "https://www.volkswagengroupcom",
        "status": "public",
        "market_cap": 90.0,
        "employees": 640000,
        "ceo": "Oliver Blume"
    },
    "gm": {
        "id": "gm",
        "name": "General Motors Company",
        "ticker": "GM",
        "company_type": "competitor",
        "sector": "Automotive",
        "description": "American automaker pivoting to electric and autonomous vehicles. Competing with Tesla on Ultium battery platform and autonomous tech.",
        "founded_year": 1908,
        "headquarters": "Detroit, Michigan, USA",
        "website": "https://www.gm.com",
        "status": "public",
        "market_cap": 55.0,
        "employees": 170000,
        "ceo": "Mary Barra"
    },
    "microsoft": {
        "id": "microsoft",
        "name": "Microsoft Corporation",
        "ticker": "MSFT",
        "company_type": "competitor",
        "sector": "Technology/AI",
        "description": "Tech giant and major OpenAI investor. Competes with Tesla on autonomous vehicles and with xAI on AI models through Copilot.",
        "founded_year": 1975,
        "headquarters": "Redmond, Washington, USA",
        "website": "https://www.microsoft.com",
        "status": "public",
        "market_cap": 3100.0,
        "employees": 220000,
        "ceo": "Satya Nadella"
    },
    "tiktok": {
        "id": "tiktok",
        "name": "TikTok (ByteDance)",
        "ticker": None,
        "company_type": "competitor",
        "sector": "Social Media",
        "description": "Chinese short-form video platform. Competes with Meta on social media and user engagement. Growing global presence.",
        "founded_year": 2016,
        "headquarters": "Beijing, China",
        "website": "https://www.tiktok.com",
        "status": "private",
        "market_cap": 75.0,
        "employees": 30000,
        "ceo": "Zhang Yiming"
    },
    "ray_ban": {
        "id": "ray_ban",
        "name": "Ray-Ban (EssilorLuxottica)",
        "ticker": None,
        "company_type": "partner",
        "sector": "Consumer Electronics/Eyewear",
        "description": "Luxury eyewear brand partnering with Meta on smart glasses. Growing wearable technology presence.",
        "founded_year": 1936,
        "headquarters": "Paris, France",
        "website": "https://www.rayban.com",
        "status": "public",
        "market_cap": 150.0,
        "employees": 100000,
        "ceo": "Francesco Milleri"
    },
    "fda": {
        "id": "fda",
        "name": "U.S. Food and Drug Administration (FDA)",
        "ticker": None,
        "company_type": "regulatory",
        "sector": "Government/Regulatory",
        "description": "U.S. regulatory agency for medical devices and pharmaceuticals. Approves Neuralink human implant trials and medical device regulations.",
        "founded_year": 1906,
        "headquarters": "Silver Spring, Maryland, USA",
        "website": "https://www.fda.gov",
        "status": "government",
        "market_cap": None,
        "employees": 18000,
        "ceo": "Robert M. Califf (Commissioner)"
    },
}


# ============================================================================
# RELATIONSHIPS DATABASE - 200+ RELATIONSHIPS
# ============================================================================

RELATIONSHIPS: List[Dict[str, Any]] = [
    # ========== TESLA SUPPLIER RELATIONSHIPS (15) ==========
    {
        "source_id": "tesla",
        "target_id": "nvidia",
        "relationship_type": "supplier",
        "strength": 9,
        "description": "NVIDIA supplies H100/H200 GPUs for Tesla FSD training and development",
        "bidirectional": False
    },
    {
        "source_id": "tesla",
        "target_id": "panasonic",
        "relationship_type": "supplier",
        "strength": 9,
        "description": "Panasonic supplies battery cells for Tesla vehicles, long-standing partnership since Model S",
        "bidirectional": False
    },
    {
        "source_id": "tesla",
        "target_id": "catl",
        "relationship_type": "supplier",
        "strength": 9,
        "description": "CATL supplies LFP battery cells for Tesla Model 3/Y in China and globally",
        "bidirectional": False
    },
    {
        "source_id": "tesla",
        "target_id": "lg_energy",
        "relationship_type": "supplier",
        "strength": 8,
        "description": "LG Energy supplies pouch-format battery cells for Tesla Model 3 and Model Y",
        "bidirectional": False
    },
    {
        "source_id": "tesla",
        "target_id": "samsung_sdi",
        "relationship_type": "supplier",
        "strength": 7,
        "description": "Samsung SDI supplies battery cells and power electronics components to Tesla",
        "bidirectional": False
    },
    {
        "source_id": "tesla",
        "target_id": "tsmc",
        "relationship_type": "supplier",
        "strength": 8,
        "description": "TSMC manufactures Tesla infotainment and vehicle control system chips",
        "bidirectional": False
    },
    {
        "source_id": "tesla",
        "target_id": "sk_hynix",
        "relationship_type": "supplier",
        "strength": 6,
        "description": "SK Hynix supplies memory chips (DRAM, NAND) for Tesla vehicle electronics",
        "bidirectional": False
    },
    {
        "source_id": "tesla",
        "target_id": "qualcomm",
        "relationship_type": "supplier",
        "strength": 8,
        "description": "Qualcomm supplies Snapdragon SoCs for Tesla infotainment and connectivity systems",
        "bidirectional": False
    },
    {
        "source_id": "tesla",
        "target_id": "bosch",
        "relationship_type": "supplier",
        "strength": 7,
        "description": "Bosch supplies sensors and control systems for Tesla vehicles",
        "bidirectional": False
    },
    {
        "source_id": "tesla",
        "target_id": "infineon",
        "relationship_type": "supplier",
        "strength": 8,
        "description": "Infineon supplies power semiconductors and SiC chips for Tesla drivetrain",
        "bidirectional": False
    },
    {
        "source_id": "tesla",
        "target_id": "amphenol",
        "relationship_type": "supplier",
        "strength": 7,
        "description": "Amphenol supplies high-reliability connectors for Tesla vehicle electronics",
        "bidirectional": False
    },
    {
        "source_id": "tesla",
        "target_id": "foxconn",
        "relationship_type": "supplier",
        "strength": 6,
        "description": "Foxconn provides electronics manufacturing and assembly services for Tesla components",
        "bidirectional": False
    },
    {
        "source_id": "tesla",
        "target_id": "corning",
        "relationship_type": "supplier",
        "strength": 6,
        "description": "Corning supplies glass and specialty materials for Tesla vehicles",
        "bidirectional": False
    },
    {
        "source_id": "tesla",
        "target_id": "3m",
        "relationship_type": "supplier",
        "strength": 5,
        "description": "3M supplies adhesives, tapes, and thermal management materials to Tesla",
        "bidirectional": False
    },
    {
        "source_id": "tesla",
        "target_id": "intel",
        "relationship_type": "supplier",
        "strength": 3,
        "description": "Limited Intel component usage in legacy Tesla systems",
        "bidirectional": False
    },

    # ========== SPACEX SUPPLIER RELATIONSHIPS (8) ==========
    {
        "source_id": "spacex",
        "target_id": "nvidia",
        "relationship_type": "supplier",
        "strength": 7,
        "description": "NVIDIA GPUs used in SpaceX onboard computing and ground station systems",
        "bidirectional": False
    },
    {
        "source_id": "spacex",
        "target_id": "tsmc",
        "relationship_type": "supplier",
        "strength": 8,
        "description": "TSMC manufactures avionics and flight control system chips for SpaceX rockets",
        "bidirectional": False
    },
    {
        "source_id": "spacex",
        "target_id": "amphenol",
        "relationship_type": "supplier",
        "strength": 7,
        "description": "Amphenol supplies harsh-environment connectors for SpaceX rocket and spacecraft",
        "bidirectional": False
    },
    {
        "source_id": "spacex",
        "target_id": "sk_hynix",
        "relationship_type": "supplier",
        "strength": 6,
        "description": "SK Hynix supplies radiation-hardened memory for SpaceX spacecraft avionics",
        "bidirectional": False
    },
    {
        "source_id": "spacex",
        "target_id": "infineon",
        "relationship_type": "supplier",
        "strength": 6,
        "description": "Infineon supplies power electronics for SpaceX vehicle propulsion systems",
        "bidirectional": False
    },
    {
        "source_id": "spacex",
        "target_id": "bosch",
        "relationship_type": "supplier",
        "strength": 5,
        "description": "Bosch supplies specialized sensors for SpaceX vehicle guidance and control",
        "bidirectional": False
    },
    {
        "source_id": "spacex",
        "target_id": "corning",
        "relationship_type": "supplier",
        "strength": 5,
        "description": "Corning supplies specialty optical and thermal materials for SpaceX applications",
        "bidirectional": False
    },
    {
        "source_id": "spacex",
        "target_id": "foxconn",
        "relationship_type": "supplier",
        "strength": 4,
        "description": "Foxconn provides some electronics assembly for SpaceX ground equipment",
        "bidirectional": False
    },

    # ========== XAI RELATIONSHIPS (6) ==========
    {
        "source_id": "xai",
        "target_id": "nvidia",
        "relationship_type": "supplier",
        "strength": 10,
        "description": "NVIDIA H100/H200 GPUs critical for xAI model training and Grok development",
        "bidirectional": False
    },
    {
        "source_id": "xai",
        "target_id": "x_twitter",
        "relationship_type": "integration",
        "strength": 9,
        "description": "Grok integrated into X/Twitter platform, data access for model training",
        "bidirectional": True
    },
    {
        "source_id": "xai",
        "target_id": "openai",
        "relationship_type": "competitor",
        "strength": 9,
        "description": "Direct competition in LLM and AI reasoning capabilities",
        "bidirectional": True
    },
    {
        "source_id": "xai",
        "target_id": "anthropic",
        "relationship_type": "competitor",
        "strength": 8,
        "description": "Competition in AI safety and reasoning models",
        "bidirectional": True
    },
    {
        "source_id": "xai",
        "target_id": "google",
        "relationship_type": "competitor",
        "strength": 8,
        "description": "Competing with Google's Gemini and other AI models",
        "bidirectional": True
    },
    {
        "source_id": "xai",
        "target_id": "meta",
        "relationship_type": "competitor",
        "strength": 7,
        "description": "Competition with Meta's LLaMA models and AI initiatives",
        "bidirectional": True
    },

    # ========== TESLA COMPETITOR RELATIONSHIPS (10) ==========
    {
        "source_id": "tesla",
        "target_id": "byd",
        "relationship_type": "competitor",
        "strength": 10,
        "description": "Direct competition in EV sales, battery technology, and global market share",
        "bidirectional": True
    },
    {
        "source_id": "tesla",
        "target_id": "nio",
        "relationship_type": "competitor",
        "strength": 8,
        "description": "Fierce competition in Chinese premium EV market with advanced autonomous features",
        "bidirectional": True
    },
    {
        "source_id": "tesla",
        "target_id": "rivian",
        "relationship_type": "competitor",
        "strength": 8,
        "description": "Competition in premium EV segment, adventure vehicles, autonomous driving",
        "bidirectional": True
    },
    {
        "source_id": "tesla",
        "target_id": "lucid",
        "relationship_type": "competitor",
        "strength": 7,
        "description": "Direct competition in luxury EV sedan segment",
        "bidirectional": True
    },
    {
        "source_id": "tesla",
        "target_id": "google",
        "relationship_type": "competitor",
        "strength": 8,
        "description": "Waymo autonomous driving competes with Tesla FSD technology",
        "bidirectional": True
    },
    {
        "source_id": "tesla",
        "target_id": "apple",
        "relationship_type": "competitor",
        "strength": 6,
        "description": "Apple EV development and infotainment ecosystem compete with Tesla",
        "bidirectional": True
    },
    {
        "source_id": "tesla",
        "target_id": "meta",
        "relationship_type": "competitor",
        "strength": 4,
        "description": "Limited competition in autonomous tech and metaverse integration",
        "bidirectional": True
    },
    {
        "source_id": "tesla",
        "target_id": "amazon",
        "relationship_type": "competitor",
        "strength": 5,
        "description": "AWS powers competitor AI systems; limited direct EV competition",
        "bidirectional": True
    },
    {
        "source_id": "tesla",
        "target_id": "toyota",
        "relationship_type": "strategic",
        "strength": 5,
        "description": "Occasional technology licensing and strategic collaboration discussions",
        "bidirectional": True
    },
    {
        "source_id": "byd",
        "target_id": "catl",
        "relationship_type": "supplier",
        "strength": 9,
        "description": "CATL supplies majority of BYD's battery cells, vertically integrated partnership",
        "bidirectional": False
    },

    # ========== SPACEX RELATIONSHIPS (12) ==========
    {
        "source_id": "spacex",
        "target_id": "nasa",
        "relationship_type": "customer",
        "strength": 10,
        "description": "NASA contracts SpaceX for cargo and crew missions to ISS, Artemis lunar program",
        "bidirectional": False
    },
    {
        "source_id": "spacex",
        "target_id": "us_dod",
        "relationship_type": "customer",
        "strength": 9,
        "description": "DoD contracts for national security launches, Starshield, military applications",
        "bidirectional": False
    },
    {
        "source_id": "spacex",
        "target_id": "blue_origin",
        "relationship_type": "competitor",
        "strength": 9,
        "description": "Direct competition for national security launches and commercial space contracts",
        "bidirectional": True
    },
    {
        "source_id": "spacex",
        "target_id": "ula",
        "relationship_type": "competitor",
        "strength": 8,
        "description": "Competition for U.S. government and military launch contracts",
        "bidirectional": True
    },
    {
        "source_id": "spacex",
        "target_id": "faa",
        "relationship_type": "regulatory",
        "strength": 10,
        "description": "FAA regulates SpaceX launch licenses, Starship environmental reviews, reusable vehicle certification",
        "bidirectional": False
    },
    {
        "source_id": "spacex",
        "target_id": "tmobile",
        "relationship_type": "partner",
        "strength": 8,
        "description": "Starlink direct-to-cell partnership for emergency messaging and connectivity",
        "bidirectional": True
    },
    {
        "source_id": "spacex",
        "target_id": "delta",
        "relationship_type": "customer",
        "strength": 7,
        "description": "Starlink aviation customer for in-flight connectivity",
        "bidirectional": False
    },
    {
        "source_id": "spacex",
        "target_id": "amazon",
        "relationship_type": "competitor",
        "strength": 7,
        "description": "Kuiper satellite internet competes with Starlink for global broadband coverage",
        "bidirectional": True
    },
    {
        "source_id": "spacex",
        "target_id": "hertz",
        "relationship_type": "transportation",
        "strength": 4,
        "description": "Logistics partner for Starlink deployment and SpaceX operations",
        "bidirectional": False
    },
    {
        "source_id": "spacex",
        "target_id": "us_congress",
        "relationship_type": "regulatory",
        "strength": 8,
        "description": "Congressional oversight and legislation affecting space policy, subsidies, regulations",
        "bidirectional": False
    },
    {
        "source_id": "nasa",
        "target_id": "blue_origin",
        "relationship_type": "customer",
        "strength": 7,
        "description": "NASA contracts with Blue Origin for lunar lander and commercial services",
        "bidirectional": False
    },
    {
        "source_id": "nasa",
        "target_id": "ula",
        "relationship_type": "customer",
        "strength": 8,
        "description": "NASA uses ULA for national security and some civil space launches",
        "bidirectional": False
    },

    # ========== X/TWITTER RELATIONSHIPS (8) ==========
    {
        "source_id": "x_twitter",
        "target_id": "meta",
        "relationship_type": "competitor",
        "strength": 10,
        "description": "Direct competition for social media users, advertising revenue, platform dominance",
        "bidirectional": True
    },
    {
        "source_id": "x_twitter",
        "target_id": "google",
        "relationship_type": "competitor",
        "strength": 7,
        "description": "Competition for digital advertising and content distribution through Google News",
        "bidirectional": True
    },
    {
        "source_id": "x_twitter",
        "target_id": "amazon",
        "relationship_type": "strategic",
        "strength": 6,
        "description": "AWS powers X infrastructure, advertising platform integration",
        "bidirectional": False
    },
    {
        "source_id": "x_twitter",
        "target_id": "fcc",
        "relationship_type": "regulatory",
        "strength": 7,
        "description": "FCC oversight of X/Twitter broadcast regulations and spectrum usage",
        "bidirectional": False
    },
    {
        "source_id": "x_twitter",
        "target_id": "us_congress",
        "relationship_type": "regulatory",
        "strength": 8,
        "description": "Congressional oversight of X content moderation, misinformation, speech policy",
        "bidirectional": False
    },
    {
        "source_id": "x_twitter",
        "target_id": "xai",
        "relationship_type": "integration",
        "strength": 9,
        "description": "Grok AI integration into X platform, data access for xAI training",
        "bidirectional": True
    },
    {
        "source_id": "x_twitter",
        "target_id": "saudi_pif",
        "relationship_type": "investor",
        "strength": 6,
        "description": "Saudi PIF investment in X/Twitter equity and strategic partnership",
        "bidirectional": False
    },
    {
        "source_id": "x_twitter",
        "target_id": "openai",
        "relationship_type": "competitor",
        "strength": 6,
        "description": "Competition for AI integration in social media and user engagement",
        "bidirectional": True
    },

    # ========== NEURALINK RELATIONSHIPS (5) ==========
    {
        "source_id": "neuralink",
        "target_id": "fda",
        "relationship_type": "regulatory",
        "strength": 10,
        "description": "FDA regulatory approval for human trials and medical device classification",
        "bidirectional": False
    },
    {
        "source_id": "neuralink",
        "target_id": "us_congress",
        "relationship_type": "regulatory",
        "strength": 7,
        "description": "Congressional oversight of neural interface technology and bioethics",
        "bidirectional": False
    },
    {
        "source_id": "neuralink",
        "target_id": "tesla",
        "relationship_type": "synergy",
        "strength": 7,
        "description": "Technology synergies with Tesla autonomous systems and neural integration",
        "bidirectional": True
    },
    {
        "source_id": "neuralink",
        "target_id": "xai",
        "relationship_type": "synergy",
        "strength": 6,
        "description": "Potential integration with xAI for human-AI interfaces and neural data processing",
        "bidirectional": True
    },
    {
        "source_id": "neuralink",
        "target_id": "nvidia",
        "relationship_type": "supplier",
        "strength": 5,
        "description": "NVIDIA chips for real-time neural signal processing and data analysis",
        "bidirectional": False
    },

    # ========== BORING COMPANY RELATIONSHIPS (3) ==========
    {
        "source_id": "boring_company",
        "target_id": "us_congress",
        "relationship_type": "regulatory",
        "strength": 7,
        "description": "Infrastructure approvals and federal funding for underground transportation projects",
        "bidirectional": False
    },
    {
        "source_id": "boring_company",
        "target_id": "tesla",
        "relationship_type": "synergy",
        "strength": 6,
        "description": "Technology synergies and potential integration with Tesla transportation network",
        "bidirectional": True
    },
    {
        "source_id": "boring_company",
        "target_id": "bosch",
        "relationship_type": "supplier",
        "strength": 5,
        "description": "Supplier of industrial equipment and components for boring machines",
        "bidirectional": False
    },

    # ========== REGULATORY RELATIONSHIPS (15) ==========
    {
        "source_id": "tesla",
        "target_id": "nhtsa",
        "relationship_type": "regulatory",
        "strength": 9,
        "description": "NHTSA oversight of Tesla FSD safety, vehicle testing, and recall investigations",
        "bidirectional": False
    },
    {
        "source_id": "tesla",
        "target_id": "sec_gov",
        "relationship_type": "regulatory",
        "strength": 8,
        "description": "SEC disclosure requirements, Musk conduct investigations, filing oversight",
        "bidirectional": False
    },
    {
        "source_id": "tesla",
        "target_id": "epa",
        "relationship_type": "regulatory",
        "strength": 7,
        "description": "EPA environmental compliance, emission credits, battery recycling standards",
        "bidirectional": False
    },
    {
        "source_id": "tesla",
        "target_id": "california_dmv",
        "relationship_type": "regulatory",
        "strength": 9,
        "description": "California DMV autonomous vehicle testing and deployment permits for FSD",
        "bidirectional": False
    },
    {
        "source_id": "tesla",
        "target_id": "us_congress",
        "relationship_type": "regulatory",
        "strength": 7,
        "description": "Congressional oversight, EV incentives, and autonomous driving legislation",
        "bidirectional": False
    },
    {
        "source_id": "tesla",
        "target_id": "fcc",
        "relationship_type": "regulatory",
        "strength": 5,
        "description": "FCC oversight of Tesla wireless connectivity and spectrum usage",
        "bidirectional": False
    },
    {
        "source_id": "spacex",
        "target_id": "us_congress",
        "relationship_type": "regulatory",
        "strength": 8,
        "description": "Congressional oversight, space policy, and national security launch contracts",
        "bidirectional": False
    },
    {
        "source_id": "spacex",
        "target_id": "epa",
        "relationship_type": "regulatory",
        "strength": 6,
        "description": "EPA environmental impact assessments for launches and Starship testing",
        "bidirectional": False
    },
    {
        "source_id": "spacex",
        "target_id": "us_dod",
        "relationship_type": "regulatory",
        "strength": 8,
        "description": "DoD oversight of national security space launches and military applications",
        "bidirectional": False
    },
    {
        "source_id": "xai",
        "target_id": "us_congress",
        "relationship_type": "regulatory",
        "strength": 6,
        "description": "Congressional AI governance oversight and regulation development",
        "bidirectional": False
    },
    {
        "source_id": "xai",
        "target_id": "fcc",
        "relationship_type": "regulatory",
        "strength": 4,
        "description": "FCC potential oversight of AI-generated content and platform regulation",
        "bidirectional": False
    },
    {
        "source_id": "doge",
        "target_id": "tesla",
        "relationship_type": "advisory",
        "strength": 10,
        "description": "Musk leads DOGE government efficiency advisory, direct policy influence",
        "bidirectional": True
    },
    {
        "source_id": "doge",
        "target_id": "spacex",
        "relationship_type": "advisory",
        "strength": 9,
        "description": "DOGE supports SpaceX on government contracts and regulatory streamlining",
        "bidirectional": True
    },
    {
        "source_id": "doge",
        "target_id": "us_congress",
        "relationship_type": "advisory",
        "strength": 8,
        "description": "DOGE advises Congress on government efficiency and cost reduction",
        "bidirectional": False
    },
    {
        "source_id": "doge",
        "target_id": "faa",
        "relationship_type": "advisory",
        "strength": 7,
        "description": "DOGE advisory role in streamlining FAA approval processes for SpaceX",
        "bidirectional": False
    },

    # ========== INVESTOR RELATIONSHIPS (10) ==========
    {
        "source_id": "blackrock",
        "target_id": "tesla",
        "relationship_type": "investor",
        "strength": 9,
        "description": "BlackRock major institutional investor in Tesla (3%+ stake through funds)",
        "bidirectional": False
    },
    {
        "source_id": "vanguard",
        "target_id": "tesla",
        "relationship_type": "investor",
        "strength": 9,
        "description": "Vanguard major institutional investor in Tesla through index and active funds",
        "bidirectional": False
    },
    {
        "source_id": "fidelity",
        "target_id": "tesla",
        "relationship_type": "investor",
        "strength": 8,
        "description": "Fidelity significant investor in Tesla and SpaceX (secondary market)",
        "bidirectional": False
    },
    {
        "source_id": "ark_invest",
        "target_id": "tesla",
        "relationship_type": "investor",
        "strength": 9,
        "description": "ARK bullish on Tesla, major shareholder through ARKK and other ETFs",
        "bidirectional": False
    },
    {
        "source_id": "blackrock",
        "target_id": "nvidia",
        "relationship_type": "investor",
        "strength": 8,
        "description": "BlackRock major NVIDIA shareholder due to AI and semiconductor exposure",
        "bidirectional": False
    },
    {
        "source_id": "vanguard",
        "target_id": "nvidia",
        "relationship_type": "investor",
        "strength": 8,
        "description": "Vanguard significant NVIDIA investor through index and active management",
        "bidirectional": False
    },
    {
        "source_id": "fidelity",
        "target_id": "nvidia",
        "relationship_type": "investor",
        "strength": 7,
        "description": "Fidelity NVIDIA investor due to semiconductor and AI exposure",
        "bidirectional": False
    },
    {
        "source_id": "saudi_pif",
        "target_id": "x_twitter",
        "relationship_type": "investor",
        "strength": 7,
        "description": "Saudi PIF strategic investor in X/Twitter after Musk acquisition",
        "bidirectional": False
    },
    {
        "source_id": "ark_invest",
        "target_id": "nvidia",
        "relationship_type": "investor",
        "strength": 7,
        "description": "ARK bullish on NVIDIA AI and GPU technology",
        "bidirectional": False
    },
    {
        "source_id": "blackrock",
        "target_id": "google",
        "relationship_type": "investor",
        "strength": 8,
        "description": "BlackRock major Alphabet shareholder",
        "bidirectional": False
    },

    # ========== SUPPLY CHAIN RELATIONSHIPS (18) ==========
    {
        "source_id": "nvidia",
        "target_id": "tsmc",
        "relationship_type": "supplier",
        "strength": 10,
        "description": "TSMC manufactures NVIDIA's H100/H200 GPUs for xAI and other applications",
        "bidirectional": False
    },
    {
        "source_id": "nvidia",
        "target_id": "sk_hynix",
        "relationship_type": "supplier",
        "strength": 8,
        "description": "SK Hynix supplies HBM (High Bandwidth Memory) for NVIDIA GPUs",
        "bidirectional": False
    },
    {
        "source_id": "catl",
        "target_id": "byd",
        "relationship_type": "supplier",
        "strength": 9,
        "description": "CATL supplies majority of BYD's battery cells",
        "bidirectional": False
    },
    {
        "source_id": "panasonic",
        "target_id": "tesla",
        "relationship_type": "supplier",
        "strength": 9,
        "description": "Panasonic battery cell supplier for Tesla Giga Shanghai and Giga Nevada",
        "bidirectional": False
    },
    {
        "source_id": "lg_energy",
        "target_id": "rivian",
        "relationship_type": "supplier",
        "strength": 8,
        "description": "LG Energy supplies battery cells to Rivian vehicles",
        "bidirectional": False
    },
    {
        "source_id": "samsung_sdi",
        "target_id": "bmw",
        "relationship_type": "supplier",
        "strength": 8,
        "description": "Samsung SDI supplies battery cells to BMW and other OEMs",
        "bidirectional": False
    },
    {
        "source_id": "tsmc",
        "target_id": "qualcomm",
        "relationship_type": "supplier",
        "strength": 9,
        "description": "TSMC manufactures Qualcomm Snapdragon processors used in Tesla infotainment",
        "bidirectional": False
    },
    {
        "source_id": "infineon",
        "target_id": "tesla",
        "relationship_type": "supplier",
        "strength": 8,
        "description": "Infineon SiC power semiconductors essential for Tesla drivetrain efficiency",
        "bidirectional": False
    },
    {
        "source_id": "bosch",
        "target_id": "rivian",
        "relationship_type": "supplier",
        "strength": 7,
        "description": "Bosch supplies sensors and control systems to Rivian vehicles",
        "bidirectional": False
    },
    {
        "source_id": "bosch",
        "target_id": "lucid",
        "relationship_type": "supplier",
        "strength": 6,
        "description": "Bosch supplies automotive components to Lucid Motors",
        "bidirectional": False
    },
    {
        "source_id": "amphenol",
        "target_id": "rivian",
        "relationship_type": "supplier",
        "strength": 6,
        "description": "Amphenol supplies connectors for Rivian vehicle electronics",
        "bidirectional": False
    },
    {
        "source_id": "corning",
        "target_id": "byd",
        "relationship_type": "supplier",
        "strength": 6,
        "description": "Corning glass and materials supplier to BYD vehicles",
        "bidirectional": False
    },
    {
        "source_id": "foxconn",
        "target_id": "apple",
        "relationship_type": "supplier",
        "strength": 9,
        "description": "Foxconn primary manufacturing partner for Apple products",
        "bidirectional": False
    },
    {
        "source_id": "foxconn",
        "target_id": "meta",
        "relationship_type": "supplier",
        "strength": 6,
        "description": "Foxconn assembles Meta Quest VR headsets and hardware",
        "bidirectional": False
    },
    {
        "source_id": "nvidia",
        "target_id": "meta",
        "relationship_type": "supplier",
        "strength": 8,
        "description": "NVIDIA GPUs power Meta AI research and data center infrastructure",
        "bidirectional": False
    },
    {
        "source_id": "nvidia",
        "target_id": "google",
        "relationship_type": "supplier",
        "strength": 8,
        "description": "NVIDIA GPUs used for Google AI and cloud infrastructure",
        "bidirectional": False
    },
    {
        "source_id": "nvidia",
        "target_id": "amazon",
        "relationship_type": "supplier",
        "strength": 7,
        "description": "NVIDIA GPUs for AWS AI services and customer cloud AI workloads",
        "bidirectional": False
    },
    {
        "source_id": "tsmc",
        "target_id": "apple",
        "relationship_type": "supplier",
        "strength": 10,
        "description": "TSMC primary manufacturer of Apple silicon (A-series, M-series chips)",
        "bidirectional": False
    },

    # ========== STRATEGIC PARTNERSHIPS (16) ==========
    {
        "source_id": "tesla",
        "target_id": "hertz",
        "relationship_type": "customer",
        "strength": 8,
        "description": "Hertz large fleet customer for Tesla vehicles, rental network",
        "bidirectional": False
    },
    {
        "source_id": "tesla",
        "target_id": "uber",
        "relationship_type": "partner",
        "strength": 7,
        "description": "Potential robotaxi partnership and autonomous vehicle deployment",
        "bidirectional": True
    },
    {
        "source_id": "spacex",
        "target_id": "tmobile",
        "relationship_type": "partner",
        "strength": 9,
        "description": "Starlink direct-to-cell partnership for emergency messaging and connectivity",
        "bidirectional": True
    },
    {
        "source_id": "spacex",
        "target_id": "delta",
        "relationship_type": "customer",
        "strength": 7,
        "description": "Delta Air Lines customer for Starlink aviation connectivity",
        "bidirectional": False
    },
    {
        "source_id": "tesla",
        "target_id": "saudi_aramco",
        "relationship_type": "partner",
        "strength": 6,
        "description": "Energy sector partnership and technology licensing discussions",
        "bidirectional": True
    },
    {
        "source_id": "tesla",
        "target_id": "toyota",
        "relationship_type": "partner",
        "strength": 5,
        "description": "Technology licensing and collaborative development on autonomous systems",
        "bidirectional": True
    },
    {
        "source_id": "nasa",
        "target_id": "spacex",
        "relationship_type": "customer",
        "strength": 10,
        "description": "SpaceX primary ISS resupply and crew vehicle, Artemis lunar program",
        "bidirectional": False
    },
    {
        "source_id": "us_dod",
        "target_id": "spacex",
        "relationship_type": "customer",
        "strength": 9,
        "description": "SpaceX national security launches and Starshield defense applications",
        "bidirectional": False
    },
    {
        "source_id": "tmobile",
        "target_id": "spacex",
        "relationship_type": "partner",
        "strength": 9,
        "description": "T-Mobile and Starlink direct-to-cell partnership for messaging",
        "bidirectional": True
    },
    {
        "source_id": "uber",
        "target_id": "google",
        "relationship_type": "partner",
        "strength": 7,
        "description": "Waymo autonomous vehicles for Uber ride-sharing integration",
        "bidirectional": True
    },
    {
        "source_id": "apple",
        "target_id": "bmw",
        "relationship_type": "partner",
        "strength": 6,
        "description": "Apple CarPlay integration in BMW vehicles",
        "bidirectional": True
    },
    {
        "source_id": "amazon",
        "target_id": "rivian",
        "relationship_type": "customer",
        "strength": 8,
        "description": "Amazon large customer for Rivian electric delivery vans (EDV)",
        "bidirectional": False
    },
    {
        "source_id": "google",
        "target_id": "bmw",
        "relationship_type": "partner",
        "strength": 7,
        "description": "Google Android Automotive integration in BMW vehicles",
        "bidirectional": True
    },
    {
        "source_id": "meta",
        "target_id": "ray_ban",
        "relationship_type": "partner",
        "strength": 7,
        "description": "Meta Ray-Ban smart glasses product collaboration",
        "bidirectional": True
    },
    {
        "source_id": "openai",
        "target_id": "microsoft",
        "relationship_type": "partner",
        "strength": 9,
        "description": "Microsoft strategic investor and cloud infrastructure partner for OpenAI",
        "bidirectional": True
    },
    {
        "source_id": "anthropic",
        "target_id": "google",
        "relationship_type": "investor",
        "strength": 8,
        "description": "Google major investor in Anthropic for cloud and AI partnership",
        "bidirectional": False
    },

    # ========== COMPETITIVE DYNAMICS (14) ==========
    {
        "source_id": "openai",
        "target_id": "anthropic",
        "relationship_type": "competitor",
        "strength": 9,
        "description": "Direct competition in LLM development and AI products",
        "bidirectional": True
    },
    {
        "source_id": "openai",
        "target_id": "meta",
        "relationship_type": "competitor",
        "strength": 8,
        "description": "Competition in AI models and LLaMA vs ChatGPT positioning",
        "bidirectional": True
    },
    {
        "source_id": "openai",
        "target_id": "google",
        "relationship_type": "competitor",
        "strength": 9,
        "description": "ChatGPT competes with Google's Gemini and search dominance",
        "bidirectional": True
    },
    {
        "source_id": "anthropic",
        "target_id": "google",
        "relationship_type": "competitor",
        "strength": 7,
        "description": "Claude competes with Google's Gemini and AI solutions",
        "bidirectional": True
    },
    {
        "source_id": "anthropic",
        "target_id": "meta",
        "relationship_type": "competitor",
        "strength": 6,
        "description": "Competition with Meta's LLaMA models in open-source AI",
        "bidirectional": True
    },
    {
        "source_id": "blue_origin",
        "target_id": "ula",
        "relationship_type": "competitor",
        "strength": 7,
        "description": "Competition for commercial and military space contracts",
        "bidirectional": True
    },
    {
        "source_id": "rivian",
        "target_id": "lucid",
        "relationship_type": "competitor",
        "strength": 8,
        "description": "Competition in premium American EV market",
        "bidirectional": True
    },
    {
        "source_id": "nio",
        "target_id": "byd",
        "relationship_type": "competitor",
        "strength": 9,
        "description": "Chinese EV market competition for market share and technology leadership",
        "bidirectional": True
    },
    {
        "source_id": "amazon",
        "target_id": "spacex",
        "relationship_type": "competitor",
        "strength": 7,
        "description": "Kuiper vs Starlink satellite internet competition",
        "bidirectional": True
    },
    {
        "source_id": "google",
        "target_id": "amazon",
        "relationship_type": "competitor",
        "strength": 8,
        "description": "Google vs Amazon AWS cloud computing competition",
        "bidirectional": True
    },
    {
        "source_id": "apple",
        "target_id": "google",
        "relationship_type": "competitor",
        "strength": 8,
        "description": "iPhone vs Android, privacy, services ecosystem competition",
        "bidirectional": True
    },
    {
        "source_id": "apple",
        "target_id": "samsung",
        "relationship_type": "competitor",
        "strength": 9,
        "description": "iPhone vs Galaxy smartphone market competition",
        "bidirectional": True
    },
    {
        "source_id": "meta",
        "target_id": "tiktok",
        "relationship_type": "competitor",
        "strength": 9,
        "description": "Facebook/Instagram Reels vs TikTok short-form video competition",
        "bidirectional": True
    },
    {
        "source_id": "amazon",
        "target_id": "meta",
        "relationship_type": "competitor",
        "strength": 6,
        "description": "Competition in digital advertising and retail ecosystems",
        "bidirectional": True
    },

    # ========== CROSS-MUSK SYNERGIES (8) ==========
    {
        "source_id": "tesla",
        "target_id": "spacex",
        "relationship_type": "synergy",
        "strength": 8,
        "description": "Shared technologies: batteries, power systems, autonomous control systems",
        "bidirectional": True
    },
    {
        "source_id": "tesla",
        "target_id": "xai",
        "relationship_type": "synergy",
        "strength": 7,
        "description": "FSD uses xAI models for reasoning and decision making in autonomous driving",
        "bidirectional": True
    },
    {
        "source_id": "tesla",
        "target_id": "neuralink",
        "relationship_type": "synergy",
        "strength": 6,
        "description": "Potential human-AI integration for vehicle control and autonomous systems",
        "bidirectional": True
    },
    {
        "source_id": "spacex",
        "target_id": "boring_company",
        "relationship_type": "synergy",
        "strength": 5,
        "description": "Infrastructure and tunneling technologies shared across companies",
        "bidirectional": True
    },
    {
        "source_id": "xai",
        "target_id": "neuralink",
        "relationship_type": "synergy",
        "strength": 6,
        "description": "Neural interface potential for direct xAI model access and control",
        "bidirectional": True
    },
    {
        "source_id": "tesla",
        "target_id": "x_twitter",
        "relationship_type": "synergy",
        "strength": 7,
        "description": "Vehicle software updates, user feedback, and product announcements via X",
        "bidirectional": True
    },
    {
        "source_id": "spacex",
        "target_id": "x_twitter",
        "relationship_type": "synergy",
        "strength": 7,
        "description": "Starlink internet powers X/Twitter infrastructure and global connectivity",
        "bidirectional": True
    },
    {
        "source_id": "boring_company",
        "target_id": "x_twitter",
        "relationship_type": "synergy",
        "strength": 3,
        "description": "X marketing and communication channel for Boring Company projects",
        "bidirectional": False
    },

    # ========== ADDITIONAL KEY RELATIONSHIPS (12) ==========
    {
        "source_id": "epa",
        "target_id": "tesla",
        "relationship_type": "regulatory",
        "strength": 7,
        "description": "EPA environmental compliance and EV emission credit tracking",
        "bidirectional": False
    },
    {
        "source_id": "fcc",
        "target_id": "spacex",
        "relationship_type": "regulatory",
        "strength": 8,
        "description": "FCC spectrum allocation and Starlink broadband regulatory approval",
        "bidirectional": False
    },
    {
        "source_id": "nvidia",
        "target_id": "openai",
        "relationship_type": "supplier",
        "strength": 9,
        "description": "NVIDIA supplies GPUs for OpenAI's ChatGPT training and inference",
        "bidirectional": False
    },
    {
        "source_id": "nvidia",
        "target_id": "anthropic",
        "relationship_type": "supplier",
        "strength": 8,
        "description": "NVIDIA GPUs for Claude model training at Anthropic",
        "bidirectional": False
    },
    {
        "source_id": "tsmc",
        "target_id": "nvidia",
        "relationship_type": "supplier",
        "strength": 10,
        "description": "TSMC manufactures NVIDIA H100/H200 GPUs at 4nm/3nm nodes",
        "bidirectional": False
    },
    {
        "source_id": "samsung_sdi",
        "target_id": "tesla",
        "relationship_type": "supplier",
        "strength": 6,
        "description": "Samsung SDI battery cell supplier for Tesla vehicles",
        "bidirectional": False
    },
    {
        "source_id": "sk_hynix",
        "target_id": "nvidia",
        "relationship_type": "supplier",
        "strength": 9,
        "description": "SK Hynix HBM memory for NVIDIA H100/H200 GPUs critical for AI",
        "bidirectional": False
    },
    {
        "source_id": "qualcomm",
        "target_id": "rivian",
        "relationship_type": "supplier",
        "strength": 6,
        "description": "Qualcomm infotainment and connectivity chips in Rivian vehicles",
        "bidirectional": False
    },
    {
        "source_id": "infineon",
        "target_id": "rivian",
        "relationship_type": "supplier",
        "strength": 7,
        "description": "Infineon power semiconductors for Rivian EV drivetrain",
        "bidirectional": False
    },
    {
        "source_id": "panasonic",
        "target_id": "toyota",
        "relationship_type": "supplier",
        "strength": 7,
        "description": "Panasonic battery supplier for Toyota hybrid and EV vehicles",
        "bidirectional": False
    },
    {
        "source_id": "catl",
        "target_id": "volkswagen",
        "relationship_type": "supplier",
        "strength": 8,
        "description": "CATL major battery supplier for Volkswagen Group EVs",
        "bidirectional": False
    },
    {
        "source_id": "lg_energy",
        "target_id": "gm",
        "relationship_type": "supplier",
        "strength": 8,
        "description": "LG Energy joint venture with GM for battery supply (Ultium)",
        "bidirectional": False
    },

    # ========== ADDITIONAL 50+ RELATIONSHIPS ==========
    {
        "source_id": "samsung",
        "target_id": "apple",
        "relationship_type": "competitor",
        "strength": 9,
        "description": "Samsung Galaxy vs Apple iPhone smartphone competition",
        "bidirectional": True
    },
    {
        "source_id": "samsung",
        "target_id": "tesla",
        "relationship_type": "competitor",
        "strength": 5,
        "description": "Samsung consumer electronics compete with Tesla ecosystem products",
        "bidirectional": True
    },
    {
        "source_id": "bmw",
        "target_id": "tesla",
        "relationship_type": "competitor",
        "strength": 8,
        "description": "BMW luxury EVs compete directly with Tesla Model S/X/3",
        "bidirectional": True
    },
    {
        "source_id": "bmw",
        "target_id": "google",
        "relationship_type": "partner",
        "strength": 7,
        "description": "Android Automotive integration in BMW vehicles",
        "bidirectional": True
    },
    {
        "source_id": "volkswagen",
        "target_id": "tesla",
        "relationship_type": "competitor",
        "strength": 9,
        "description": "VW ID.family EVs compete with Tesla across segments",
        "bidirectional": True
    },
    {
        "source_id": "volkswagen",
        "target_id": "catl",
        "relationship_type": "supplier",
        "strength": 8,
        "description": "CATL major battery supplier for Volkswagen Group EVs",
        "bidirectional": False
    },
    {
        "source_id": "volkswagen",
        "target_id": "tesla",
        "relationship_type": "strategic",
        "strength": 4,
        "description": "Technology licensing discussions on EV platforms",
        "bidirectional": True
    },
    {
        "source_id": "gm",
        "target_id": "tesla",
        "relationship_type": "competitor",
        "strength": 8,
        "description": "GM EVs and autonomous driving compete with Tesla",
        "bidirectional": True
    },
    {
        "source_id": "gm",
        "target_id": "lg_energy",
        "relationship_type": "supplier",
        "strength": 9,
        "description": "Ultium battery joint venture between GM and LG Energy",
        "bidirectional": True
    },
    {
        "source_id": "gm",
        "target_id": "lg_energy",
        "relationship_type": "partner",
        "strength": 10,
        "description": "Joint venture for battery production and supply",
        "bidirectional": True
    },
    {
        "source_id": "microsoft",
        "target_id": "openai",
        "relationship_type": "investor",
        "strength": 10,
        "description": "Microsoft major investor ($13B+) and strategic partnership with OpenAI",
        "bidirectional": False
    },
    {
        "source_id": "microsoft",
        "target_id": "tesla",
        "relationship_type": "competitor",
        "strength": 6,
        "description": "Copilot AI competition with xAI and FSD technology",
        "bidirectional": True
    },
    {
        "source_id": "microsoft",
        "target_id": "google",
        "relationship_type": "competitor",
        "strength": 8,
        "description": "Copilot vs Bard/Gemini AI assistant competition",
        "bidirectional": True
    },
    {
        "source_id": "microsoft",
        "target_id": "anthropic",
        "relationship_type": "investor",
        "strength": 6,
        "description": "Microsoft investor in Anthropic for diversified AI strategy",
        "bidirectional": False
    },
    {
        "source_id": "tiktok",
        "target_id": "meta",
        "relationship_type": "competitor",
        "strength": 10,
        "description": "TikTok vs Meta Reels intense competition for short-form video",
        "bidirectional": True
    },
    {
        "source_id": "tiktok",
        "target_id": "google",
        "relationship_type": "competitor",
        "strength": 7,
        "description": "TikTok competes with YouTube for video content and creators",
        "bidirectional": True
    },
    {
        "source_id": "tiktok",
        "target_id": "x_twitter",
        "relationship_type": "competitor",
        "strength": 6,
        "description": "Competition for user time and attention on social platforms",
        "bidirectional": True
    },
    {
        "source_id": "ray_ban",
        "target_id": "meta",
        "relationship_type": "partner",
        "strength": 8,
        "description": "Ray-Ban Meta smart glasses product partnership",
        "bidirectional": True
    },
    {
        "source_id": "ray_ban",
        "target_id": "apple",
        "relationship_type": "competitor",
        "strength": 6,
        "description": "Competition with Apple Vision Pro in AR/VR wearables",
        "bidirectional": True
    },
    {
        "source_id": "qualcomm",
        "target_id": "apple",
        "relationship_type": "supplier",
        "strength": 7,
        "description": "Qualcomm modems for iPhones (until recent Apple switch to in-house)",
        "bidirectional": False
    },
    {
        "source_id": "bosch",
        "target_id": "tesla",
        "relationship_type": "supplier",
        "strength": 7,
        "description": "Bosch sensors and control systems for Tesla vehicles",
        "bidirectional": False
    },
    {
        "source_id": "bosch",
        "target_id": "volkswagen",
        "relationship_type": "supplier",
        "strength": 8,
        "description": "Bosch major supplier for VW automotive components",
        "bidirectional": False
    },
    {
        "source_id": "bosch",
        "target_id": "bmw",
        "relationship_type": "supplier",
        "strength": 8,
        "description": "Bosch supplier for BMW vehicle systems and components",
        "bidirectional": False
    },
    {
        "source_id": "tsmc",
        "target_id": "google",
        "relationship_type": "supplier",
        "strength": 8,
        "description": "TSMC manufactures Google Tensor chips for Pixel phones",
        "bidirectional": False
    },
    {
        "source_id": "tsmc",
        "target_id": "samsung",
        "relationship_type": "competitor",
        "strength": 8,
        "description": "TSMC vs Samsung for semiconductor foundry dominance",
        "bidirectional": True
    },
    {
        "source_id": "infineon",
        "target_id": "gm",
        "relationship_type": "supplier",
        "strength": 6,
        "description": "Infineon power semiconductors for GM EV drivetrain",
        "bidirectional": False
    },
    {
        "source_id": "infineon",
        "target_id": "volkswagen",
        "relationship_type": "supplier",
        "strength": 7,
        "description": "Infineon SiC and IGBT chips for VW ID.family EVs",
        "bidirectional": False
    },
    {
        "source_id": "amphenol",
        "target_id": "bmw",
        "relationship_type": "supplier",
        "strength": 6,
        "description": "Amphenol connectors for BMW vehicle electronics",
        "bidirectional": False
    },
    {
        "source_id": "amphenol",
        "target_id": "volkswagen",
        "relationship_type": "supplier",
        "strength": 6,
        "description": "Amphenol connectors for Volkswagen Group vehicles",
        "bidirectional": False
    },
    {
        "source_id": "corning",
        "target_id": "apple",
        "relationship_type": "supplier",
        "strength": 8,
        "description": "Corning Gorilla Glass for iPhone and Apple devices",
        "bidirectional": False
    },
    {
        "source_id": "panasonic",
        "target_id": "rivian",
        "relationship_type": "supplier",
        "strength": 6,
        "description": "Panasonic battery supplier for some Rivian applications",
        "bidirectional": False
    },
    {
        "source_id": "panasonic",
        "target_id": "byd",
        "relationship_type": "competitor",
        "strength": 7,
        "description": "Panasonic and BYD compete in battery manufacturing",
        "bidirectional": True
    },
    {
        "source_id": "catl",
        "target_id": "gm",
        "relationship_type": "supplier",
        "strength": 7,
        "description": "CATL exploring battery supply partnerships with GM",
        "bidirectional": False
    },
    {
        "source_id": "catl",
        "target_id": "rivian",
        "relationship_type": "supplier",
        "strength": 5,
        "description": "CATL potential battery supplier for Rivian",
        "bidirectional": False
    },
    {
        "source_id": "lg_energy",
        "target_id": "tesla",
        "relationship_type": "supplier",
        "strength": 8,
        "description": "LG Energy battery supplier for Tesla Model 3/Y",
        "bidirectional": False
    },
    {
        "source_id": "lg_energy",
        "target_id": "bmw",
        "relationship_type": "supplier",
        "strength": 7,
        "description": "LG Energy battery supplier for BMW EVs",
        "bidirectional": False
    },
    {
        "source_id": "samsung_sdi",
        "target_id": "rivian",
        "relationship_type": "supplier",
        "strength": 6,
        "description": "Samsung SDI battery supplier for Rivian vehicles",
        "bidirectional": False
    },
    {
        "source_id": "samsung_sdi",
        "target_id": "lucid",
        "relationship_type": "supplier",
        "strength": 7,
        "description": "Samsung SDI battery supplier for Lucid Motors",
        "bidirectional": False
    },
    {
        "source_id": "foxconn",
        "target_id": "google",
        "relationship_type": "supplier",
        "strength": 6,
        "description": "Foxconn manufactures Google Pixel phones",
        "bidirectional": False
    },
    {
        "source_id": "foxconn",
        "target_id": "microsoft",
        "relationship_type": "supplier",
        "strength": 5,
        "description": "Foxconn assembles Surface devices and Xbox hardware",
        "bidirectional": False
    },
    {
        "source_id": "sk_hynix",
        "target_id": "apple",
        "relationship_type": "supplier",
        "strength": 6,
        "description": "SK Hynix memory supplier for iPhone and Apple devices",
        "bidirectional": False
    },
    {
        "source_id": "sk_hynix",
        "target_id": "samsung",
        "relationship_type": "competitor",
        "strength": 9,
        "description": "SK Hynix vs Samsung in memory chip market dominance",
        "bidirectional": True
    },
    {
        "source_id": "qualcomm",
        "target_id": "samsung",
        "relationship_type": "supplier",
        "strength": 8,
        "description": "Qualcomm Snapdragon chips for Samsung Galaxy phones",
        "bidirectional": False
    },
    {
        "source_id": "qualcomm",
        "target_id": "google",
        "relationship_type": "supplier",
        "strength": 7,
        "description": "Qualcomm modems for older Pixel phones",
        "bidirectional": False
    },
    {
        "source_id": "nvidia",
        "target_id": "microsoft",
        "relationship_type": "supplier",
        "strength": 8,
        "description": "NVIDIA GPUs for Microsoft Azure AI services",
        "bidirectional": False
    },
    {
        "source_id": "nvidia",
        "target_id": "intel",
        "relationship_type": "competitor",
        "strength": 8,
        "description": "NVIDIA vs Intel GPU/AI chip market competition",
        "bidirectional": True
    },
    {
        "source_id": "intel",
        "target_id": "tsmc",
        "relationship_type": "competitor",
        "strength": 7,
        "description": "Intel vs TSMC semiconductor manufacturing competition",
        "bidirectional": True
    },
    {
        "source_id": "fda",
        "target_id": "neuralink",
        "relationship_type": "regulatory",
        "strength": 10,
        "description": "FDA regulatory oversight of Neuralink brain implants",
        "bidirectional": False
    },
    {
        "source_id": "nhtsa",
        "target_id": "rivian",
        "relationship_type": "regulatory",
        "strength": 7,
        "description": "NHTSA vehicle safety testing and oversight of Rivian",
        "bidirectional": False
    },
    {
        "source_id": "nhtsa",
        "target_id": "lucid",
        "relationship_type": "regulatory",
        "strength": 7,
        "description": "NHTSA vehicle safety oversight of Lucid Motors",
        "bidirectional": False
    },
    {
        "source_id": "nhtsa",
        "target_id": "byd",
        "relationship_type": "regulatory",
        "strength": 6,
        "description": "NHTSA potential oversight if BYD expands to US market",
        "bidirectional": False
    },
    {
        "source_id": "sec_gov",
        "target_id": "tesla",
        "relationship_type": "regulatory",
        "strength": 8,
        "description": "SEC oversight of Tesla public company disclosures",
        "bidirectional": False
    },
    {
        "source_id": "sec_gov",
        "target_id": "rivian",
        "relationship_type": "regulatory",
        "strength": 6,
        "description": "SEC oversight of Rivian public company filings",
        "bidirectional": False
    },
    {
        "source_id": "epa",
        "target_id": "spacex",
        "relationship_type": "regulatory",
        "strength": 6,
        "description": "EPA environmental impact assessment for SpaceX launches",
        "bidirectional": False
    },
    {
        "source_id": "epa",
        "target_id": "volkswagen",
        "relationship_type": "regulatory",
        "strength": 7,
        "description": "EPA emissions testing and EV compliance oversight",
        "bidirectional": False
    },
    {
        "source_id": "fcc",
        "target_id": "amazon",
        "relationship_type": "regulatory",
        "strength": 7,
        "description": "FCC spectrum regulation for Kuiper satellite internet",
        "bidirectional": False
    },
    {
        "source_id": "fcc",
        "target_id": "meta",
        "relationship_type": "regulatory",
        "strength": 6,
        "description": "FCC oversight of Meta's wireless and broadcast operations",
        "bidirectional": False
    },
    {
        "source_id": "us_congress",
        "target_id": "google",
        "relationship_type": "regulatory",
        "strength": 8,
        "description": "Congressional antitrust and tech regulation oversight of Google",
        "bidirectional": False
    },
    {
        "source_id": "us_congress",
        "target_id": "meta",
        "relationship_type": "regulatory",
        "strength": 8,
        "description": "Congressional oversight of Meta content moderation and antitrust",
        "bidirectional": False
    },
    {
        "source_id": "us_congress",
        "target_id": "amazon",
        "relationship_type": "regulatory",
        "strength": 7,
        "description": "Congressional antitrust investigations of Amazon",
        "bidirectional": False
    },
    {
        "source_id": "us_congress",
        "target_id": "apple",
        "relationship_type": "regulatory",
        "strength": 7,
        "description": "Congressional App Store and antitrust oversight of Apple",
        "bidirectional": False
    },
    {
        "source_id": "us_congress",
        "target_id": "openai",
        "relationship_type": "regulatory",
        "strength": 6,
        "description": "Congressional AI regulation and oversight of OpenAI",
        "bidirectional": False
    },
    {
        "source_id": "us_congress",
        "target_id": "anthropic",
        "relationship_type": "regulatory",
        "strength": 5,
        "description": "Congressional oversight of AI development at Anthropic",
        "bidirectional": False
    },
    {
        "source_id": "blue_origin",
        "target_id": "nasa",
        "relationship_type": "customer",
        "strength": 8,
        "description": "Blue Origin Blue Moon lunar lander contracts with NASA",
        "bidirectional": False
    },
    {
        "source_id": "ula",
        "target_id": "nasa",
        "relationship_type": "customer",
        "strength": 7,
        "description": "ULA national security launches for NASA and DoD",
        "bidirectional": False
    },
    {
        "source_id": "amazon",
        "target_id": "rivian",
        "relationship_type": "customer",
        "strength": 9,
        "description": "Amazon orders 100K+ Rivian electric delivery vans",
        "bidirectional": False
    },
    {
        "source_id": "rivian",
        "target_id": "samsung_sdi",
        "relationship_type": "supplier",
        "strength": 6,
        "description": "Samsung SDI battery supplier for Rivian vehicles",
        "bidirectional": False
    },
    {
        "source_id": "lucid",
        "target_id": "panasonic",
        "relationship_type": "supplier",
        "strength": 5,
        "description": "Panasonic potential battery supplier for Lucid vehicles",
        "bidirectional": False
    },
    {
        "source_id": "hertz",
        "target_id": "rivian",
        "relationship_type": "customer",
        "strength": 6,
        "description": "Hertz rental fleet customer for Rivian vehicles",
        "bidirectional": False
    },
    {
        "source_id": "uber",
        "target_id": "rivian",
        "relationship_type": "partner",
        "strength": 6,
        "description": "Uber potential autonomous vehicle partner with Rivian",
        "bidirectional": True
    },
    {
        "source_id": "microsoft",
        "target_id": "tesla",
        "relationship_type": "partner",
        "strength": 5,
        "description": "Potential cloud and AI partnerships between Tesla and Microsoft",
        "bidirectional": True
    },
    {
        "source_id": "blackrock",
        "target_id": "spacex",
        "relationship_type": "investor",
        "strength": 5,
        "description": "BlackRock investor in SpaceX through secondary markets",
        "bidirectional": False
    },
    {
        "source_id": "vanguard",
        "target_id": "spacex",
        "relationship_type": "investor",
        "strength": 5,
        "description": "Vanguard investor in SpaceX through secondary markets",
        "bidirectional": False
    },
    {
        "source_id": "fidelity",
        "target_id": "xai",
        "relationship_type": "investor",
        "strength": 4,
        "description": "Fidelity potential investor in xAI growth rounds",
        "bidirectional": False
    },
    {
        "source_id": "ark_invest",
        "target_id": "spacex",
        "relationship_type": "investor",
        "strength": 6,
        "description": "ARK bullish on SpaceX and space economy",
        "bidirectional": False
    },
]


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_company(company_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve a company by its ID.

    Args:
        company_id: The unique identifier for the company

    Returns:
        Company dictionary or None if not found
    """
    return COMPANIES.get(company_id)


def get_relationships_for(company_id: str) -> List[Dict[str, Any]]:
    """
    Retrieve all relationships involving a specific company.

    Args:
        company_id: The unique identifier for the company

    Returns:
        List of relationship dictionaries where company is source or target
    """
    relationships = []
    for rel in RELATIONSHIPS:
        if rel["source_id"] == company_id or rel["target_id"] == company_id:
            relationships.append(rel)
    return relationships


def get_companies_by_type(company_type: str) -> List[Dict[str, Any]]:
    """
    Filter companies by their type.

    Args:
        company_type: Type to filter by (e.g., "supplier", "competitor", "core_musk")

    Returns:
        List of company dictionaries matching the type
    """
    return [
        company for company in COMPANIES.values()
        if company["company_type"] == company_type
    ]


def get_ecosystem_graph() -> Dict[str, Any]:
    """
    Generate ecosystem graph formatted for D3.js visualization.

    Returns:
        Dictionary with 'nodes' and 'links' for D3 visualization
    """
    nodes = []
    node_ids = set()

    # Add all companies as nodes
    for company_id, company_data in COMPANIES.items():
        node_ids.add(company_id)
        nodes.append({
            "id": company_id,
            "name": company_data["name"],
            "type": company_data["company_type"],
            "sector": company_data["sector"],
            "ticker": company_data["ticker"],
            "status": company_data["status"],
            "market_cap": company_data["market_cap"],
        })

    # Create links from relationships
    links = []
    for rel in RELATIONSHIPS:
        links.append({
            "source": rel["source_id"],
            "target": rel["target_id"],
            "type": rel["relationship_type"],
            "strength": rel["strength"],
            "description": rel["description"],
            "bidirectional": rel["bidirectional"],
        })

    return {
        "nodes": nodes,
        "links": links,
        "metadata": {
            "total_companies": len(nodes),
            "total_relationships": len(links),
            "generated": datetime.now().isoformat(),
        }
    }


def search_companies(query: str) -> List[Dict[str, Any]]:
    """
    Fuzzy search companies by name or ticker.

    Args:
        query: Search string (name or ticker)

    Returns:
        List of matching company dictionaries, sorted by match quality
    """
    query_lower = query.lower()
    matches = []

    for company_id, company_data in COMPANIES.items():
        name = company_data["name"].lower()
        ticker = (company_data["ticker"] or "").lower()

        # Exact matches
        if name == query_lower or ticker == query_lower:
            matches.append((company_data, 1.0))
        # Substring matches
        elif query_lower in name or query_lower in ticker:
            matches.append((company_data, 0.8))
        # Fuzzy matches
        else:
            name_ratio = difflib.SequenceMatcher(None, query_lower, name).ratio()
            ticker_ratio = difflib.SequenceMatcher(None, query_lower, ticker).ratio()
            best_ratio = max(name_ratio, ticker_ratio)

            if best_ratio > 0.6:
                matches.append((company_data, best_ratio))

    # Sort by match quality (descending)
    matches.sort(key=lambda x: x[1], reverse=True)
    return [company for company, _ in matches]


def get_relationship_strength_stats() -> Dict[str, float]:
    """
    Calculate statistics about relationship strengths.

    Returns:
        Dictionary with average, min, max relationship strengths
    """
    if not RELATIONSHIPS:
        return {"average": 0, "min": 0, "max": 0, "total": 0}

    strengths = [rel["strength"] for rel in RELATIONSHIPS]
    return {
        "average": sum(strengths) / len(strengths),
        "min": min(strengths),
        "max": max(strengths),
        "total": len(strengths),
    }


def get_company_statistics() -> Dict[str, Any]:
    """
    Generate statistics about companies in the ecosystem.

    Returns:
        Dictionary with company count by type and sector
    """
    stats = {
        "total_companies": len(COMPANIES),
        "by_type": {},
        "by_sector": {},
        "by_status": {},
    }

    for company in COMPANIES.values():
        # Count by type
        company_type = company["company_type"]
        stats["by_type"][company_type] = stats["by_type"].get(company_type, 0) + 1

        # Count by sector
        sector = company["sector"]
        stats["by_sector"][sector] = stats["by_sector"].get(sector, 0) + 1

        # Count by status
        status = company["status"]
        stats["by_status"][status] = stats["by_status"].get(status, 0) + 1

    return stats


def get_top_connected_companies(limit: int = 10) -> List[Tuple[str, int]]:
    """
    Get companies with the most relationships.

    Args:
        limit: Maximum number of companies to return

    Returns:
        List of (company_id, relationship_count) tuples, sorted by count
    """
    connection_counts: Dict[str, int] = {}

    for rel in RELATIONSHIPS:
        source = rel["source_id"]
        target = rel["target_id"]

        connection_counts[source] = connection_counts.get(source, 0) + 1
        if rel["bidirectional"]:
            connection_counts[target] = connection_counts.get(target, 0) + 1
        else:
            connection_counts[target] = connection_counts.get(target, 0) + 1

    # Sort by count (descending)
    sorted_companies = sorted(
        connection_counts.items(),
        key=lambda x: x[1],
        reverse=True
    )

    return sorted_companies[:limit]


# ============================================================================
# MODULE INITIALIZATION
# ============================================================================

if __name__ == "__main__":
    # Example usage and basic validation
    print("=== Musk Ecosystem Intelligence Module ===\n")

    # Statistics
    stats = get_company_statistics()
    print(f"Total Companies: {stats['total_companies']}")
    print(f"Total Relationships: {len(RELATIONSHIPS)}\n")

    print("Companies by Type:")
    for company_type, count in stats["by_type"].items():
        print(f"  {company_type}: {count}")

    print("\nTop 10 Most Connected Companies:")
    for company_id, count in get_top_connected_companies(10):
        company = COMPANIES[company_id]
        print(f"  {company['name']}: {count} relationships")

    print("\nRelationship Strength Statistics:")
    strength_stats = get_relationship_strength_stats()
    print(f"  Average Strength: {strength_stats['average']:.2f}")
    print(f"  Range: {strength_stats['min']} - {strength_stats['max']}")

    print("\nSample Search: 'NVIDIA'")
    results = search_companies("nvidia")
    if results:
        for company in results[:3]:
            print(f"  {company['name']} ({company['ticker']})")
