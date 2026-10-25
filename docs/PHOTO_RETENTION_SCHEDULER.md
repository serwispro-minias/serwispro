# Scheduled service-order photo cleanup (Windows)

The application does not start a scheduler inside web workers. The cleanup is a
safe, repeatable Flask CLI command:

```powershell
Set-Location C:\serwispro
C:\serwispro\venv\Scripts\python.exe -m flask --app run.py cleanup-service-order-photos
```

To run it daily, create a Task Scheduler task (run as the Windows account that
has access to the application database and private `uploads` directory):

1. Open **Task Scheduler** → **Create Basic Task** and name it
   `SerwisPRO order-photo cleanup`.
2. Choose **Daily** and a low-traffic time (for example 02:30).
3. Choose **Start a program**:
   - Program: `C:\serwispro\venv\Scripts\python.exe`
   - Arguments: `-m flask --app run.py cleanup-service-order-photos`
   - Start in: `C:\serwispro`
4. In task properties, enable **Run whether user is logged on or not** if
   appropriate for the deployment account, and set a retry on failure.
5. Run the task manually once and inspect **Last Run Result** and the configured
   application logs.

The command is registered by the app, but creating a Windows Scheduled Task is
an installation/deployment action and is not performed automatically by the
application or this code change.