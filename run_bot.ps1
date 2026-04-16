# Auto-restart script for trading bot
# This script will restart the bot if it crashes

while ($true) {
    Write-Host "Starting trading bot..."
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Write-Host "[$timestamp] Bot started"

    try {
        # Activate virtual environment and run bot
        & .\.venv\Scripts\python.exe main.py
        $exit_code = $LASTEXITCODE

        if ($exit_code -eq 0) {
            Write-Host "Bot exited normally (exit code 0)"
            break
        } else {
            Write-Host "Bot crashed with exit code $exit_code"
            Write-Host "Restarting in 10 seconds..."
            Start-Sleep -Seconds 10
        }
    } catch {
        Write-Host "Error running bot: $_"
        Write-Host "Restarting in 10 seconds..."
        Start-Sleep -Seconds 10
    }
}
