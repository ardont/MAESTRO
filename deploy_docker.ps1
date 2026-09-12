$ErrorActionPreference = "Stop"

$RemoteUser = "todaisy"
$RemoteIP = "100.111.189.72"
$RemoteDir = "/Users/todaisy/rlt_project"

Write-Host "1. Uploading Docker files and project files..." -ForegroundColor Yellow
scp -o StrictHostKeyChecking=no Dockerfile docker-compose.yml requirements.txt "${RemoteUser}@${RemoteIP}:${RemoteDir}/"
scp -r -o StrictHostKeyChecking=no RLT_project "${RemoteUser}@${RemoteIP}:${RemoteDir}/"
scp -r -o StrictHostKeyChecking=no dataset  "${RemoteUser}@${RemoteIP}:${RemoteDir}/"

Write-Host "`n2. Starting Docker Compose on the server..." -ForegroundColor Yellow
$RemoteCommand = @"
cd $RemoteDir
echo 'Building and starting Docker containers...'
docker compose up --build -d
echo 'Containers are running! You can check logs with: docker compose logs -f'
"@

ssh -o StrictHostKeyChecking=no ${RemoteUser}@${RemoteIP} $RemoteCommand

Write-Host "`nDone! ML service is running on the server." -ForegroundColor Green
