# HW1-1 Domain Name System

2026 NAP  
Chung-Yu Hsu <hsuchy@it.cs.nycu.edu.tw>

Spec is also available on HackMD (login required).

## Requirement

In this homework, you are requested to build a series of DNS servers:

- two authoritative name servers
  - one primary
  - one secondary
- one internal resolver

You may use any DNS server software you want, but only **BIND9** is tested and guaranteed to pass.

## Networking

### Original network topology

The initial topology contains:

- **VPN server**
  - connected by `wg client` links
- **Router**
  - DMZ-side IP: `172.16.0.254`
  - Private-side IP: `172.16.1.254`
  - also associated with VPN subnet `192.168.x.y/28`
- **DMZ zone**
  - subnet: `172.16.0.0/24`
  - also associated with VPN subnet `192.168.x.y/28`
  - contains:
    - **Agent** at `172.16.0.123`
    - **Client**
- **Private zone**
  - subnet: `172.16.1.0/24`
  - contains:
    - **Internal Agent** at `172.16.1.123`

The Router has a DNAT path toward the DMZ Agent and Internal Agent.

### Updated network topology

The updated topology adds DNS components:

- **VPN server** with `wg client` connections to:
  - Router
  - Client
  - NS
- **DMZ zone** (`172.16.0.0/24`, VPN subnet `192.168.x.y/28`)
  - **Agent** at `172.16.0.123`
  - **Client**
  - **NS** at `172.16.0.53`
- **Private zone** (`172.16.1.0/24`)
  - **Internal Agent** at `172.16.1.123`
  - **Private NS** at `172.16.1.53`
  - **DNS** at `172.16.1.153`
- **Router**
  - `172.16.0.254`
  - `172.16.1.254`

The Router still provides DNAT toward the DMZ Agent.

### Firewall

The firewall diagram defines directional intent between zones and services.

Legend used by the slide:

- grey solid arrow: established/return traffic
- green dashed arrow: allowed connection
- red dashed arrow with `X`: blocked/rejected connection

#### DMZ <-> Private-zone rules

- **DMZ -> Private NS** is allowed to specified services.
  - Footnote `*1`: destination port `55688` and `53`
- **DMZ -> DNS** is blocked by default.
- **Private -> DMZ** is allowed by default for return/approved access as shown in the diagram.

#### Private-zone -> VPN-side rules

- **Private NS -> VPN Server** is allowed to specified services through NAT on the Router.
  - Footnote `*2`: `192.168.255.{1-3}` on port `53`
- **DNS -> VPN Server** is blocked for all traffic as shown.

#### VPN-side connectivity

- The **VPN Server** has allowed bidirectional connectivity with other VPN subnets.

## Primary name server

### Basic setting

- IP: `172.16.1.53`
- FQDN: `private-ns.${ID}.nasa.`

### Requirement overview

- Serve as the primary NS.
- Resolve zone `${ID}.nasa` and the corresponding reverse zone.
- Must **not** resolve any records outside your designated zone.
- Listen for update requests.
- Transfer zone data to the secondary server.

Notes:

- The name server for zone `nasa` is at `192.168.255.1`.
- Run the WireGuard tools to get the ID from the tool output.
- You can also calculate the ID manually using the appendix method.

### Private primary NS structure

- The primary NS resides in the **Private zone**.
- It is **not meant to be queried from outside**.
  - External query handling is the responsibility of the secondary NS.
- `private-ns.${ID}.nasa.` should be untouchable from outside.
- It should appear as the **MNAME** of your SOA record.

### Zone and view

You should have **two views** in your managed zones:

- **private view**: from the DMZ zone and Private zone
- **public view**: from anywhere else

You should at least add the records listed below to those zones.

### Forward zone

#### Public view

Zone `${ID}.nasa`:

- `router A <your router VPN IP>`
- `client A <your client VPN IP>`
- `ns A <your secondary NS VPN IP>`
- `agent A <your router VPN IP>`
- `internal-agent A <your router VPN IP>`

For NS and SOA records, determine them yourself.

#### Private view

Zone `${ID}.nasa`:

- `router A 172.16.0.254`
- `ns A 172.16.0.53`
- `agent A 172.16.0.123`
- `router A 172.16.1.254`
- `private-ns A 172.16.1.53`
- `dns A 172.16.1.153`
- `internal-agent A 172.16.1.123`

For NS and SOA records, determine them yourself.

### Reverse zone

- Determine the PTR, NS, and SOA records yourself.
- For the `192.168` reverse zone, the homework uses **classless in-addr.arpa subnet delegation**.
  - Assume your VPN subnet is `192.168.x.y`
  - Your reverse zone will be `{ID}-sub28.{x}.168.192.in-addr.arpa`
- For the `172.16.{0|1}` reverse zone, it is straightforward.

## DNSSEC

- Sign all zones you manage.
  - **Except** the reverse zones for private IPs, i.e. `172.16.{0|1}`
  - You may still sign those zones if you want, but they will not be checked.
- Use:
  - algorithm **13** (`ECDSAP256SHA256`)
  - digest **2** (`SHA-256`)
- Upload your DS records via the OJ tool.
  - Upload DS for:
    - `{ID}.nasa`
    - `{ID}-sub28.{x}.168.192.in-addr.arpa`

Generate DS records with:

```bash
dig @172.16.1.53 <zone> DNSKEY | dnssec-dsfromkey -f - <zone>
```

## Dynamic zone

- Support dynamic updates with a TSIG key.
  - Generate the key yourself and upload it to OJ via the tool.
- Zone / record update policy:
  - In `{ID}.nasa`, **only** allow updating the A records of:
    - `dynamic1.{ID}.nasa`
    - `dynamic2.{ID}.nasa`
    - `dynamic3.{ID}.nasa`
    - `dynamic4.{ID}.nasa`
  - In `{0|1}.16.172.in-addr.arpa`, **only** allow updating PTR records.

## Zone transfer

- Allow zone transfer requests from the secondary NS.
- IXFR is optional,
  - as long as the whole transfer process completes within **10 seconds**.
- Notify the secondary NS on zone updates.

## Secondary name server

### Basic setting

- IP: `172.16.0.53`
- FQDN: `ns.${ID}.nasa.`

### Requirement

- The secondary NS should be a **read-only replica** of the primary NS.
- Most requirements are the same as for the primary NS.
  - Exception: the secondary NS should **not** be updatable or transferable.

## Internal resolver

### Basic setting

- IP: `172.16.1.153`
- FQDN: `dns.${ID}.nasa.`

### Requirement overview

- The internal resolver is for internal services to query.
- It should handle both:
  - the custom domain (for example `nasa.`)
  - all other domains

### Recursive resolution and forwarding

- Resolve `nasa.` and `168.192.in-addr.arpa`:
  - recursively from the root server `192.168.255.1`
- For `{ID}.nasa.` and `16.172.in-addr.arpa`:
  - you should get answers from the **private view** instead
- Resolve all other domains via Cloudflare DNS `1.1.1.1`
- Only allow requests from the **DMZ** and **Private zone**

Note: if recursive resolution of `nasa.` is difficult, `static-stub` and `trust-anchors` may be helpful.

### Validate DNSSEC

- Validate all answers under `nasa.` and `168.192.in-addr.arpa`
  - including `{ID}.nasa`
- You should see the **AD bit** set in the response flag from your resolver.

## Grading

- HW1-1 is worth **25%** of the whole HW1 grade.

### Authoritative DNS: 45%

- Forward: `10%`
  - public view: `5%`
  - private view: `5%`
- Reverse: `10%`
  - public view: `5%`
  - private view: `5%`
- Secondary NS: `12%`
- Dynamic update: `13%`
  - updated results appear on both primary and secondary servers: `10%`

### Resolver: 20%

- Can resolve queries properly: `20%`
  - resolve queries to `nasa.` and the corresponding reverse zone: `15%`
  - other zones: `5%`

### DNSSEC: 35%

- Your authoritative NS can be trusted by the OJ resolver: `10%`
  - forward + reverse: `10%`
- Your resolver can validate the chain of trust and authenticate data in responses: `25%`
  - forward (under `nasa.`): `12%`
  - reverse (under `168.192.in-addr.arpa`): `13%`

## Appendix

### Getting your subnet

After you run the WireGuard tools, you should be assigned one VPN subnet and three IPs:

- Router: first IP in your subnet
- Clients: second IP in your subnet
- NS: third IP in your subnet

Then derive your subnet from your IP.

Example:

- if your router IP is `192.168.8.17`
- then your subnet is `192.168.8.16`

### Getting your ID

If your subnet is `192.168.x.y`, then your ID is:

```text
x * 16 + y / 16
```

This formula is specific to this homework.

## References

- Understanding views in BIND 9, with examples
- Using DNSTAP with BIND
- BIND9 document
- How To Ask Questions The Smart Way / 提問的智慧
- NA/NAP/SA Google forum

## Reminder

- HW 1-2 (Mail) and HW 1-3 (LDAP) will be released in the following weeks.
  - Follow the course schedule on the NASA Course Website.
- Deadline for all homework assignments: **6/22 at 23:59 (UTC+8)**.
- You need to pass **all** test cases for HW1-0 through HW1-3 **simultaneously**.
  - Otherwise you will not receive full credit for HW1.
- The course recommends using an **IaC** approach to manage your homework environment.
  - Example: Ansible

## Good Luck!

Closing illustration content:

- A cartoon green turtle points toward the viewer.
- Text above the turtle: **"You have been blessed by good luck turtle!"**
- Text beside the turtle: **"Please save me"**
- Text below the turtle: **"(He will be ded if you don't finish your homework)"**
