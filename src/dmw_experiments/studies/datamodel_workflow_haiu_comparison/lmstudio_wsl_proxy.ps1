<#
.SYNOPSIS
Expose LM Studio's Windows loopback listener to WSL through a TCP relay.

.DESCRIPTION
Run this script in Windows PowerShell while LM Studio listens on
127.0.0.1:1234. WSL clients can then use the Windows host address and
ListenPort as their OpenAI-compatible endpoint.

The default listener binds every Windows interface. Restrict access with
Windows Firewall, or pass the address of the WSL virtual adapter through
ListenAddress.

.EXAMPLE
.\lmstudio_wsl_proxy.ps1 -ListenPort 1235
#>

param(
    [string]$ListenAddress = "0.0.0.0",
    [int]$ListenPort = 1235,
    [string]$TargetHost = "127.0.0.1",
    [int]$TargetPort = 1234
)

$ErrorActionPreference = "Stop"

$proxySource = @'
using System;
using System.Net;
using System.Net.Sockets;
using System.Threading;
using System.Threading.Tasks;

public static class WslTcpProxy
{
    public static async Task RunAsync(
        string listenAddress,
        int listenPort,
        string targetHost,
        int targetPort,
        CancellationToken cancellationToken)
    {
        var listener = new TcpListener(
            IPAddress.Parse(listenAddress),
            listenPort);
        listener.Start();
        Console.WriteLine(
            string.Format(
                "LM Studio WSL proxy listening on {0}:{1} "
                + "and forwarding to {2}:{3}",
                listenAddress,
                listenPort,
                targetHost,
                targetPort));

        try
        {
            while (!cancellationToken.IsCancellationRequested)
            {
                var client = await listener.AcceptTcpClientAsync();
                Task relay = RelayAsync(client, targetHost, targetPort);
            }
        }
        finally
        {
            listener.Stop();
        }
    }

    private static async Task RelayAsync(
        TcpClient client,
        string targetHost,
        int targetPort)
    {
        using (client)
        using (var target = new TcpClient())
        using (var relayCancellation = new CancellationTokenSource())
        {
            try
            {
                client.NoDelay = true;
                await target.ConnectAsync(targetHost, targetPort);
                target.NoDelay = true;

                var clientStream = client.GetStream();
                var targetStream = target.GetStream();
                var upstream = clientStream.CopyToAsync(
                    targetStream,
                    81920,
                    relayCancellation.Token);
                var downstream = targetStream.CopyToAsync(
                    clientStream,
                    81920,
                    relayCancellation.Token);

                await Task.WhenAny(upstream, downstream);
                relayCancellation.Cancel();

                try
                {
                    await Task.WhenAll(upstream, downstream);
                }
                catch (OperationCanceledException)
                {
                }
            }
            catch (Exception error)
            {
                Console.Error.WriteLine(
                    "Proxy connection failed: " + error.Message);
            }
        }
    }
}
'@

Add-Type -TypeDefinition $proxySource -Language CSharp
$cancellation = [System.Threading.CancellationToken]::None
[WslTcpProxy]::RunAsync(
    $ListenAddress,
    $ListenPort,
    $TargetHost,
    $TargetPort,
    $cancellation
).GetAwaiter().GetResult()
