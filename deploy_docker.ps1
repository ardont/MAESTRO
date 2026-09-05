$ErrorActionPreference = "Stop"

$RemoteUser = "rama"
$RemoteIP = "100.100.89.45"
$RemoteDir = "/home/rama/rlt_project"

Write-Host "1. Uploading Docker files and project files..." -ForegroundColor Yellow
scp -o StrictHostKeyChecking=no Dockerfile docker-compose.yml requirements.txt "${RemoteUser}@${RemoteIP}:${RemoteDir}/"
scp -r -o StrictHostKeyChecking=no RLT_project scripts "${RemoteUser}@${RemoteIP}:${RemoteDir}/"
scp -r -o StrictHostKeyChecking=no dataset txt_dataset "${RemoteUser}@${RemoteIP}:${RemoteDir}/"

Write-Host "`n2. Starting Docker Compose on the server..." -ForegroundColor Yellow
$RemoteCommand = @"
cd $RemoteDir
echo 'Building and starting Docker containers...'
sudo docker compose up --build -d
echo 'Containers are running! You can check logs with: sudo docker compose logs -f'
"@

ssh -o StrictHostKeyChecking=no ${RemoteUser}@${RemoteIP} $RemoteCommand

Write-Host "`nDone! ML service is running on the server." -ForegroundColor Green
