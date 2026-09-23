@echo off
chcp 65001 >nul
rem Run the Cloudflare tunnel for design.dev-bim.com -> localhost:9090
cd /d "%USERPROFILE%\.cloudflared"
cloudflared tunnel --config config-design.yml run design
pause
