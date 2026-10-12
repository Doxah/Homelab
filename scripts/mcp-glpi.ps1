# Lance le serveur MCP GLPI (stdio) pour Claude Desktop, secrets SOPS chargés en mémoire (aucun fichier en clair).
# Appelé par Claude Desktop : voir mcp/glpi/README.md.
# IMPORTANT : rien ne doit être écrit sur stdout, réservé au protocole MCP (erreurs -> stderr).
$ErrorActionPreference = 'Stop'

$version = '3.2.0'   # version figée ; code vérifié identique au source GitHub (commit b76b33d)
$secrets = Join-Path $PSScriptRoot '..\mcp\glpi\secrets.sops.env'

$lines = & sops --decrypt --output-type dotenv $secrets
if ($LASTEXITCODE -ne 0) {
    [Console]::Error.WriteLine("mcp-glpi : impossible de déchiffrer $secrets (clé age absente ?)")
    exit 1
}
foreach ($line in $lines) {
    if ($line -match '^\s*([A-Z0-9_]+)=(.*)$') {
        [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2], 'Process')
    }
}

# Start-Process -NoNewWindow : le processus enfant hérite directement de stdin/stdout (PowerShell ne réencode pas le flux)
$p = Start-Process -FilePath 'npx.cmd' -ArgumentList '-y', "mcp-glpi@$version" -NoNewWindow -Wait -PassThru
exit $p.ExitCode
