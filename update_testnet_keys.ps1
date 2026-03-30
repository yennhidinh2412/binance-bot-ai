# Update Binance Testnet API Keys
# Chạy script này và nhập Secret Key từ Binance Testnet

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "BINANCE TESTNET - UPDATE API KEYS" -ForegroundColor Yellow  
Write-Host "========================================`n" -ForegroundColor Cyan

$configPath = "config.py"

# Read current config
$config = Get-Content $configPath -Raw

Write-Host "Current API Key:" -ForegroundColor Green
Write-Host "WVoejz3nm3RN4NAcCSK4HELvPbD4MHnX1mZXuHYRW397OjZva1vIV3WqELMfzv7G`n" -ForegroundColor White

Write-Host "Please enter your Binance Testnet SECRET KEY:" -ForegroundColor Yellow
Write-Host "(The one shown as ******** in your screenshot)" -ForegroundColor Gray
$secretKey = Read-Host "Secret Key"

if ($secretKey -and $secretKey.Length -gt 0) {
    # Update config with new secret key
    $config = $config -replace 'BINANCE_SECRET_KEY = \([^)]+\)', "BINANCE_SECRET_KEY = (`n        `"$secretKey`"`n    )"
    
    # Save updated config
    $config | Set-Content $configPath -NoNewline
    
    Write-Host "`n✅ Config updated successfully!" -ForegroundColor Green
    Write-Host "`nConfiguration:" -ForegroundColor Cyan
    Write-Host "- Testnet: ENABLED" -ForegroundColor Green
    Write-Host "- Demo Mode: DISABLED" -ForegroundColor Yellow
    Write-Host "- API URL: https://testnet.binancefuture.com" -ForegroundColor White
    Write-Host "`nYou can now run the bot with Binance Testnet!`n" -ForegroundColor Green
} else {
    Write-Host "`n❌ Secret Key không được để trống!" -ForegroundColor Red
}

Write-Host "========================================`n" -ForegroundColor Cyan
