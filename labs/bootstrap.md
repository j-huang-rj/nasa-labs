# HW1-0 - Environment Setup

Author: bjhuang

## Homework 1 notice

- Homework 1-0 does **not** count toward the final grade, but all later parts depend on it.
- HW 1-1 (DNS), HW 1-2 (Mail), and HW 1-3 (LDAP) will be released according to the NASA course website schedule.
  - They will not be released earlier than scheduled.
- Deadline for all homework assignments: **6/22 at 23:59 (UTC+8)**.

## Purpose

- Build two network zones:
  - **DMZ**
    - VPN, Mail, WWW reverse proxy, etc.
  - **Private zone**
    - DHCP, DNS, LDAP, WWW backend, etc.
- Learn the configuration and management of these services.

## Overview

- **Router**
  - Has direct Internet access.
  - Provides NAT and firewalling.
  - Connects all VMs in the intranet.
- **Agent**
  - Simulates simple VMs inside the two zones so the TA and OJ can verify results.
- **Client (optional)**
  - Any VM you want for testing or for running services.

## Definitions

- **OJ**
  - Online Judge system: <https://nasaoj-v3.it.cs.nycu.edu.tw/>
- **VPN server**
  - A WireGuard server that connects your intranet so that the OJ worker can access it.
- **Internet**
  - IP addresses that are not in the course intranet.
- **Intranet**
  - A network zone including the VPN zone, DMZ, and your private zone, all managed by yourself.
- **VPN zone**
  - A private network provided via WireGuard configuration for you and accessible by the online judge.
- **DMZ**
  - `172.16.0.0/24`, demilitarized zone.
- **Private zone**
  - `172.16.1.0/24`, a subnet of the intranet managed by yourself.
  - It should not have direct Internet access.

## What is DMZ?

- The network zone between the private zone and the Internet.
- Traffic from the DMZ to the LAN should be monitored or checked by a firewall.

### Diagram interpretation

The slide's DMZ example shows this conceptual structure:

`Enterprise LAN -> Firewall -> DMZ network -> Firewall -> Internet`

Inside the **DMZ network** are:

- a **Router**
- a **Web server**
- a **Mail server**

Source: *What is a DMZ in Networking? | Definition from TechTarget*

## Topology

### Diagram interpretation

The topology consists of:

- **Internet** outside the intranet.
- **VPN server** outside the intranet.
- A central **Router & Firewall** connected to:
  - the Internet
  - the VPN server
  - the DMZ interface `172.16.0.254`
  - the Private-zone interface `172.16.1.254`
- **Intranet**, which contains two subnets:
  - **DMZ**: `172.16.0.x/24`
    - contains one **Agent** and one optional **Client**
    - these nodes also sit inside the **VPN zone** `192.168.x.x/28`
    - the VPN server connects directly to these VPN-zone nodes
  - **Private zone**: `172.16.1.x/24`
    - contains one **Agent** and one optional **Client**

Important visual constraint shown in the slide:

- Traffic from the **DMZ** toward the **Private zone** is marked with a large blocked symbol, indicating restricted/blocked access by default.

## Requirements

### Routing

#### Router

- Any OS is allowed.
- This VM must have these interfaces:
  - **External** for Internet access
  - **VPN zone** for OJ access
  - **DMZ**: `172.16.0.254/24`
  - **Private zone**: `172.16.1.254/24`

#### Routing behavior

- All inbound and outbound traffic for the **Private zone** must go through the Router.
- Traffic from the **Private zone** to the Internet should be NAT-masqueraded.
- Set DNAT to both agents:
  - Router port `10001` -> DMZ agent port `2222`
  - Router port `10002` -> Private-zone agent port `2222`

### Setup agent

#### Agent VMs

- OJ will log in to **Agent containers** to judge your system.
- Set up two VMs:
  - one inside the **DMZ** with IP `172.16.0.123`
  - one inside the **Private zone** with IP `172.16.1.123`
- Install Docker on both agent VMs.
  - Reference: *Install | Docker Docs*

#### Agent container

- Each Agent is a Docker container inside your VM.
- Container image download link:
  - <https://nextcloud.it.cs.nycu.edu.tw/s/JGbHmEe5Pz5PxDm>
- Start the Docker container with the specified image.
  - This enables the Agents' `2222` and `55688` ports for connection.
- Do **not** modify any settings inside the container.

```bash
wget https://nextcloud.it.cs.nycu.edu.tw/public.php/dav/files/JGbHmEe5Pz5PxDm -O agent.tar
docker load < agent.tar
docker run -d --restart unless-stopped --name nap-agent --network host nap-agent
```

Note: the slide visually emphasizes `--network host` as important.

### Firewall

- Configure firewall rules on the Router.

Rules:

- By default, all connections from other zones to the **Private zone** should be rejected.
- By default, all connections from the **Private zone** to the **VPN zone** should be rejected.
- **DMZ -> Private zone** should be allowed on port `55688`.
- ICMP connections from anywhere to anywhere are allowed.
- Internet access for both the **DMZ** and **Private zone** should be allowed.
- SSH connections from the **VPN zone** to the **Router** should be rejected.
- SSH connections from the **Router** to both **Agents** should be allowed.

## OJ checkpoints

1. Router's VPN connection
2. Router's DNAT to Agents in two zones
3. Two Agents' Internet connection
4. Trace route from Agent in Private zone
5. Check firewall rules for Router
6. Check firewall rules for Private zone

## Help / references

- Previous SA slides
  - *SA - 2025 課程內容 | NASA Course Website*
- Appendix in previous NA slides
  - <https://site.nasa.cs.nycu.edu.tw/na/2024/HW1.pdf>
- How To Ask Questions The Smart Way
  - <https://github.com/ryanhanwu/How-To-Ask-Questions-The-Smart-Way>

## Good Luck!

---

This slide is a plain closing slide with no additional substantive content beyond “Good Luck!”.
