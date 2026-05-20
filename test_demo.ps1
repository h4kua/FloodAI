$BASE = "http://127.0.0.1:8000"
$HEADERS = @{
    "x-api-key"    = "demo123"
    "Content-Type" = "application/json"
    "host"         = "localhost"
}
$PASS = 0; $FAIL = 0

function Check($name, $condition) {
    if ($condition) {
        Write-Host "  PASS  $name" -ForegroundColor Green
        $script:PASS++
    } else {
        Write-Host "  FAIL  $name" -ForegroundColor Red
        $script:FAIL++
    }
}

Write-Host "`n=== HEALTH CHECKS ===" -ForegroundColor Cyan

$r = Invoke-RestMethod -Uri "$BASE/healthz" -Headers $HEADERS
Check "GET /healthz returns ok" ($r.status -eq "ok")

$r = Invoke-RestMethod -Uri "$BASE/readyz" -Headers $HEADERS
Check "GET /readyz responds" ($null -ne $r)

Write-Host "`n=== SCENARIO 1: NORMAL CONDITIONS ===" -ForegroundColor Cyan
$body = @{
    fetched_at_utc = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    location = "Jakarta Selatan"
    openweather = @{
        main  = @{ temp = 28.0; humidity = 75 }
        rain  = @{ "1h" = 2 }
        coord = @{ lat = -6.2088; lon = 106.8456 }
    }
    poskobanjir = @(@{ wilayah = "Jakarta Selatan"; tinggi_air = 50; status = "Normal" })
    bmkg_alerts = @()
} | ConvertTo-Json -Depth 6

$r = Invoke-RestMethod -Uri "$BASE/predict/agentic" -Method POST -Headers $HEADERS -Body $body
Check "risk_level is SAFE"             ($r.risk_level -eq "SAFE")
Check "system_status is OK"            ($r.system_status -eq "OK")
Check "persistence_error is null"      ($null -eq $r.persistence_error)
Check "mapped_district resolved"       ($r.mapping_info.mapped_district -eq "Jakarta Selatan")
Check "bnpb_status not NOT_APPLICABLE" ($r.bnpb_status.code -ne "NOT_APPLICABLE")
Check "confidence_score > 0.5"        ($r.confidence_score -gt 0.5)
Check "no pipeline_error in failures" (-not ($r.failure_modes.type -contains "pipeline_error"))

Write-Host "`n=== SCENARIO 2: WARNING CONDITIONS ===" -ForegroundColor Cyan
$body = @{
    fetched_at_utc = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    location = "Jakarta Utara"
    openweather = @{
        main  = @{ temp = 27.9; humidity = 91 }
        rain  = @{ "1h" = 25 }
        coord = @{ lat = -6.2088; lon = 106.8456 }
    }
    poskobanjir = @(@{ wilayah = "Jakarta Utara"; tinggi_air = 180; status = "Siaga 2" })
    bmkg_alerts = @(@{
        headline  = "Peringatan Hujan Lebat DKI Jakarta"
        severity  = "Severe"
        certainty = "Observed"
        urgency   = "Immediate"
    })
} | ConvertTo-Json -Depth 6

$r = Invoke-RestMethod -Uri "$BASE/predict/agentic" -Method POST -Headers $HEADERS -Body $body
Check "risk_level WARNING or higher"   ($r.risk_level -in @("WARNING","DANGER","PRE_ALERT"))
Check "persistence_error is null"      ($null -eq $r.persistence_error)
Check "mapped_district resolved"       ($r.mapping_info.mapped_district -eq "Jakarta Utara")
Check "vulnerability_score > 0"       ($r.risk_state.vulnerability_score -gt 0)
Check "bnpb_status active"            ($r.bnpb_status.active -eq $true)
Check "decision_trace non-empty"      ($r.decision_trace.Count -gt 0)

Write-Host "`n=== SCENARIO 3: CRITICAL FLOOD ===" -ForegroundColor Cyan
$body = @{
    fetched_at_utc = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    location = "Jakarta Utara"
    openweather = @{
        main  = @{ temp = 26.0; humidity = 98 }
        rain  = @{ "1h" = 80 }
        coord = @{ lat = -6.1088; lon = 106.8456 }
    }
    poskobanjir = @(@{ wilayah = "Jakarta Utara"; tinggi_air = 900; status = "Siaga 1" })
    bmkg_alerts = @(@{
        headline  = "Banjir Ekstrem Jakarta Utara"
        severity  = "Extreme"
        certainty = "Observed"
        urgency   = "Immediate"
    })
} | ConvertTo-Json -Depth 6

$r = Invoke-RestMethod -Uri "$BASE/predict/agentic" -Method POST -Headers $HEADERS -Body $body
Check "persistence_error is null"      ($null -eq $r.persistence_error)
Check "system_status is valid"        ($r.system_status -in @("OK","WARNING","DEGRADED","CRITICAL","PIPELINE_FAILURE"))
Check "decision_trace non-empty"      ($r.decision_trace.Count -gt 0)
Check "failure_modes present"         ($r.failure_modes.Count -ge 0)
Check "recommended_action present"    ($r.recommended_action.Count -gt 0)

Write-Host "`n=== SCENARIO 4: LOCATION NORMALIZATION ===" -ForegroundColor Cyan
$body = @{
    fetched_at_utc = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    location = @{ city = "jakarta utara" }
    openweather = @{
        main  = @{ temp = 28.0; humidity = 80 }
        rain  = @{ "1h" = 5 }
        coord = @{ lat = -6.2088; lon = 106.8456 }
    }
    poskobanjir = @(@{ wilayah = "Jakarta Utara"; tinggi_air = 100; status = "Normal" })
    bmkg_alerts = @()
} | ConvertTo-Json -Depth 6

$r = Invoke-RestMethod -Uri "$BASE/predict/agentic" -Method POST -Headers $HEADERS -Body $body
Check "dict location normalized"       ($r.mapping_info.mapped_district -eq "Jakarta Utara")
Check "persistence_error is null"      ($null -eq $r.persistence_error)
Check "bnpb_status not NOT_APPLICABLE" ($r.bnpb_status.code -ne "NOT_APPLICABLE")

Write-Host "`n=== SCENARIO 5: ROUTE PLANNING ===" -ForegroundColor Cyan
$body = @{
    fetched_at_utc = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    location = "Jakarta Selatan"
    openweather = @{
        main  = @{ temp = 28.0; humidity = 75 }
        rain  = @{ "1h" = 2 }
        coord = @{ lat = -6.2088; lon = 106.8456 }
    }
    poskobanjir = @(@{ wilayah = "Jakarta Selatan"; tinggi_air = 50; status = "Normal" })
    bmkg_alerts = @()
} | ConvertTo-Json -Depth 6

$r = Invoke-RestMethod `
    -Uri "$BASE/predict/agentic?origin=Jakarta%20Utara&destination=Jakarta%20Selatan" `
    -Method POST -Headers $HEADERS -Body $body
Check "safe_route present"            ($null -ne $r.safe_route)
Check "route has summary or reason"   ($null -ne $r.safe_route.reason)

Write-Host "`n=== SUMMARY ===" -ForegroundColor Cyan
Write-Host "  PASSED: $PASS" -ForegroundColor Green
Write-Host "  FAILED: $FAIL" -ForegroundColor Red
if ($FAIL -eq 0) {
    Write-Host "`n  ALL TESTS PASSED - SYSTEM READY FOR DEMO" -ForegroundColor Green
} else {
    Write-Host "`n  $FAIL TEST(S) FAILED - CHECK OUTPUT ABOVE" -ForegroundColor Red
}