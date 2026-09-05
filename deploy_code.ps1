$ErrorActionPreference = "Stop"

$RemoteUser = "rama"
$RemoteIP = "100.100.89.45"
$RemoteDir = "/home/rama/rlt_project"

Write-Host "1. Uploading ONLY Code and Docker configs..." -ForegroundColor Yellow
scp -o StrictHostKeyChecking=no Dockerfile docker-compose.yml requirements.txt "${RemoteUser}@${RemoteIP}:${RemoteDir}/"
scp -r -o StrictHostKeyChecking=no RLT_project scripts "${RemoteUser}@${RemoteIP}:${RemoteDir}/"

Write-Host "`n2. Restarting Docker Compose on the server..." -ForegroundColor Yellow
$RemoteCommand = @"
cd $RemoteDir
echo 'Rebuilding and restarting Web container...'
sudo docker compose up --build -d
echo 'Containers are running! You can check logs with: sudo docker compose logs -f'
"@

ssh -o StrictHostKeyChecking=no ${RemoteUser}@${RemoteIP} $RemoteCommand

Write-Host "`nDone! Code updated and ML service is running." -ForegroundColor Green
