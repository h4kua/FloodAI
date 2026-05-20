$BASE = "http://127.0.0.1:8000"
$HEADERS = @{"x-api-key"="demo123";"Content-Type"="application/json";"host"="localhost"}

function Show-Result($label, $r) {
    Write-Host ""
    Write-Host "=============================" -ForegroundColor Yellow
    Write-Host "  $label" -ForegroundColor Yellow
    Write-Host "=============================" -ForegroundColor Yellow
    $color = if($r.risk_level -eq "SAFE"){"Green"}elseif($r.risk_level -eq "WARNING"){"DarkYellow"}else{"Red"}
    Write-Host "  risk_level    : " -NoNewline; Write-Host $r.risk_level -ForegroundColor $color
    $sc = if($r.system_status -eq "OK"){"Green"}else{"Red"}
    Write-Host "  system_status : " -NoNewline; Write-Host $r.system_status -ForegroundColor $sc
    Write-Host "  confidence    : $($r.confidence_score)"
    Write-Host "  probability   : $($r.probability)"
    Write-Host "  authority     : $($r.decision_source)"
    Write-Host "  district      : $($r.mapping_info.mapped_district)"
    Write-Host "  bnpb_code     : $($r.bnpb_status.code)"
    Write-Host "  vuln_score    : $($r.risk_state.vulnerability_score)"
    Write-Host "  exec_ms       : $($r.pipeline_execution_ms)"
    Write-Host "  persist_err   : $($r.persistence_error)"
    Write-Host ""
    Write-Host "  FAILURE MODES:" -ForegroundColor Cyan
    if ($r.failure_modes.Count -eq 0) {
        Write-Host "    (none)" -ForegroundColor Green
    } else {
        foreach ($fm in $r.failure_modes) {
            $fc = if($fm.severity -eq "critical"){"Red"}elseif($fm.severity -eq "high"){"DarkYellow"}else{"Gray"}
            Write-Host "    [$($fm.severity)] $($fm.type)" -ForegroundColor $fc
        }
    }
    Write-Host ""
    Write-Host "  ACTIONS:" -ForegroundColor Cyan
    foreach ($a in $r.recommended_action) { Write-Host "    * $a" }
    Write-Host ""
    Write-Host "  TRACE:" -ForegroundColor Cyan
    foreach ($t in $r.decision_trace) { Write-Host "    -> $t" -ForegroundColor Gray }
}

$b1 = @{
    fetched_at_utc = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    location = "Jakarta Selatan"
    openweather = @{main=@{temp=28.0;humidity=75};rain=@{"1h"=2};coord=@{lat=-6.2088;lon=106.8456}}
    poskobanjir = @(@{wilayah="Jakarta Selatan";tinggi_air=50;status="Normal"})
    bmkg_alerts = @()
} | ConvertTo-Json -Depth 6
$r1 = Invoke-RestMethod -Uri "$BASE/predict/agentic" -Method POST -Headers $HEADERS -Body $b1
Show-Result "SCENARIO 1: NORMAL - SAFE" $r1

$b2 = @{
    fetched_at_utc = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    location = "Jakarta Utara"
    openweather = @{main=@{temp=27.9;humidity=91};rain=@{"1h"=25};coord=@{lat=-6.2088;lon=106.8456}}
    poskobanjir = @(@{wilayah="Jakarta Utara";tinggi_air=180;status="Siaga 2"})
    bmkg_alerts = @(@{headline="Peringatan Hujan Lebat";severity="Severe";certainty="Observed";urgency="Immediate"})
} | ConvertTo-Json -Depth 6
$r2 = Invoke-RestMethod -Uri "$BASE/predict/agentic" -Method POST -Headers $HEADERS -Body $b2
Show-Result "SCENARIO 2: WARNING CONDITIONS" $r2

$b3 = @{
    fetched_at_utc = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    location = "Jakarta Utara"
    openweather = @{main=@{temp=26.0;humidity=98};rain=@{"1h"=80};coord=@{lat=-6.1088;lon=106.8456}}
    # Ganti tinggi_air scenario 2 dari 180 → 750 (mendekati Siaga 1)
    poskobanjir = @(@{wilayah="Jakarta Utara";tinggi_air=750;status="Siaga 2"})
    bmkg_alerts = @(@{headline="Banjir Ekstrem Jakarta Utara";severity="Extreme";certainty="Observed";urgency="Immediate"})
} | ConvertTo-Json -Depth 6
$r3 = Invoke-RestMethod -Uri "$BASE/predict/agentic" -Method POST -Headers $HEADERS -Body $b3
Show-Result "SCENARIO 3: CRITICAL FLOOD - DANGER" $r3

Write-Host "=============================" -ForegroundColor Green
Write-Host "  DEMO COMPLETE" -ForegroundColor Green
Write-Host "=============================" -ForegroundColor Green
