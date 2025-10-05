#!/usr/bin/env python3
"""
Flask应用入口文件 - 用于部署
"""

from app.main_simple import app

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=False)
