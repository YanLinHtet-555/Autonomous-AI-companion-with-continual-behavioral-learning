' Start AI Companion (tray icon + monitoring agent) - no console window
Set sh = CreateObject("WScript.Shell")
sh.Run """C:\Users\User\AppData\Local\Programs\Python\Python312\pythonw.exe"" ""D:\Git_projects\Autonomous-AI-companion-with-continual-behavioral-learning\tray_icon.py""", 0, False
