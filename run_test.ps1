$ErrorActionPreference = "Stop"

$RemoteUser = "rama"
$RemoteIP = "100.100.89.45"
$RemoteDir = "/home/rama/rlt_project"

Write-Host "1. Uploading dataset folder..." -ForegroundColor Yellow
scp -r -o StrictHostKeyChecking=no dataset "${RemoteUser}@${RemoteIP}:${RemoteDir}/"

Write-Host "2. Fixing transformers and running test..." -ForegroundColor Yellow
$RemoteCommand = @"
cd $RemoteDir
echo 'Installing fixes for RobertaModel...'
pip3 install --upgrade transformers sentence-transformers safetensors accelerate
echo 'Running indexer...'
python3 RLT_project/rag/index_knowledge_base.py --test
"@

ssh -o StrictHostKeyChecking=no ${RemoteUser}@${RemoteIP} $RemoteCommand

Write-Host "Done!" -ForegroundColor Green
