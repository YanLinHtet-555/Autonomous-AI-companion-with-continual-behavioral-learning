' Start Docker Compose — no console window
Set sh = CreateObject("WScript.Shell")
sh.Run "cmd /c cd /d ""D:\Git_projects\Autonomous-AI-companion-with-continual-behavioral-learning"" && docker compose up -d", 0, False
