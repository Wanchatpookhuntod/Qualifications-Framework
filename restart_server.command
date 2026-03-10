#!/bin/bash

cd "$(dirname "$0")"

WINDOW_TITLE="Flask-QF-Server"

# ปิด Terminal window เดิมที่ชื่อ Flask-QF-Server
osascript -e "
tell application \"Terminal\"
    repeat with w in windows
        repeat with t in tabs of w
            try
                if custom title of t is \"$WINDOW_TITLE\" then
                    close w
                    exit repeat
                end if
            end try
        end repeat
    end repeat
end tell"

sleep 0.3

# ฆ่า process บน port 5000 (ถ้ายังค้างอยู่)
PID=$(lsof -ti :5000 2>/dev/null)
[ -n "$PID" ] && kill -9 $PID 2>/dev/null

# ตั้งชื่อ window นี้ว่า Flask-QF-Server
osascript -e "tell application \"Terminal\" to set custom title of front window to \"$WINDOW_TITLE\""

# Activate virtualenv และเริ่ม Flask
source .venv/bin/activate

echo "=============================="
echo "  Flask Server"
echo "  URL: http://localhost:5000"
echo "=============================="
echo ""

python app.py
