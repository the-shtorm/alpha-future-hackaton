# Run from fastapi/ after starting the server with compose.dev.yaml.
$rankHeaders = @{ 'X-Internal-API-Key' = $env:ML_INTERNAL_API_KEY }
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/api/v1/recommendations/rank' `
    -Headers $rankHeaders -ContentType 'application/json; charset=utf-8' `
    -InFile 'examples/rank-request.json'
