# OTA Systems for Automotive Software — Study Plan & Lecture Notes

> Comprehensive study guide covering core skills, architecture concepts, and OTA system design for vehicle software engineering. Written in undergraduate/graduate lecture-note style.

---

# Table of Contents

1. [Module 1: Foundations — Linux, Networking, and Systems Programming](#module-1-foundations)
2. [Module 2: Embedded Systems & Automotive Architecture](#module-2-embedded-systems--automotive-architecture)
3. [Module 3: OTA Update Systems — Core Concepts](#module-3-ota-update-systems--core-concepts)
4. [Module 4: Security in Automotive OTA](#module-4-security-in-automotive-ota)
5. [Module 5: Backend Infrastructure & Cloud Architecture](#module-5-backend-infrastructure--cloud-architecture)
6. [Module 6: Testing & Validation](#module-6-testing--validation)
7. [Module 7: Protocols & Communication](#module-7-protocols--communication)
8. [Module 8: Build Systems, CI/CD, and Release Engineering](#module-8-build-systems-cicd-and-release-engineering)
9. [Module 9: Industry Standards & Compliance](#module-9-industry-standards--compliance)
10. [Module 10: Putting It All Together — System Design Exercise](#module-10-putting-it-all-together)
11. [Resources & Further Reading](#resources--further-reading)

---

# Module 1: Foundations

## 1.1 Linux Systems Programming

OTA update agents run on Linux-based vehicle computers (head units, telematics control units). You must be comfortable with how Linux manages processes, filesystems, and hardware.

### The Linux Boot Process

Understanding boot is critical because OTA updates often touch the bootloader.

```
Power On
  → ROM Bootloader (vendor-specific, burned into silicon)
    → U-Boot / UEFI (secondary bootloader — configurable, updateable)
      → Linux Kernel (loaded from flash/eMMC partition)
        → Init System (systemd on modern systems)
          → Userspace services (your OTA agent, vehicle middleware, etc.)
```

**Key terms:**
- **Bootloader (U-Boot)**: The first configurable software that runs. It decides *which* kernel to boot. In an A/B update scheme, U-Boot reads a flag to determine whether to boot partition A or partition B.
- **Device Tree (DTB)**: A data structure that describes hardware to the kernel. Vehicles have custom hardware, so custom device trees are common.
- **initramfs**: A temporary root filesystem loaded into RAM during boot. Sometimes used to run pre-boot update checks.

### Filesystem Layout for Embedded Linux

A typical vehicle compute unit has partitioned flash storage:

```
┌────────────────────────────────────────────────┐
│                  eMMC / NAND Flash              │
├──────────┬──────────┬──────────┬───────────────┤
│ Bootloader│ Kernel A │ Kernel B │  Boot Config  │
├──────────┼──────────┼──────────┼───────────────┤
│ RootFS A │ RootFS B │ Data     │  Recovery     │
│ (active) │ (standby)│ (persist)│  (fallback)   │
└──────────┴──────────┴──────────┴───────────────┘
```

- **A/B Partitions**: Two copies of the system. Updates are written to the inactive partition. On reboot, the bootloader switches to the updated partition.
- **Data Partition**: Persistent user data, logs, configuration. Survives updates.
- **Recovery Partition**: Minimal system for emergency recovery if both A and B fail.

### Key Linux Concepts for OTA

**Process Management:**
```bash
# The OTA agent runs as a systemd service
[Unit]
Description=OTA Update Agent
After=network-online.target

[Service]
ExecStart=/usr/bin/ota-agent --config /etc/ota/config.yaml
Restart=always
RestartSec=10
WatchdogSec=60

[Install]
WantedBy=multi-user.target
```

- `WatchdogSec=60` — systemd will restart the agent if it doesn't ping the watchdog within 60 seconds. Critical for reliability in vehicles.

**File Permissions & Capabilities:**
- The OTA agent needs root or specific capabilities to write to partitions
- `CAP_SYS_RAWIO` — for direct partition access
- `CAP_DAC_OVERRIDE` — for writing to protected directories
- Principle of least privilege: grant only what's needed

**Signals:**
- `SIGTERM` — graceful shutdown (finish current download, save state)
- `SIGKILL` — force kill (last resort, may corrupt partial download)
- The OTA agent must handle `SIGTERM` gracefully to avoid bricking a partially-updated system

### Filesystem Operations That Matter

```c
// Atomic file replacement pattern — critical for OTA
// Never update a file in-place; write to temp, then rename

int fd = open("/tmp/update.bin.tmp", O_WRONLY | O_CREAT | O_TRUNC, 0644);
write(fd, data, len);
fsync(fd);              // Flush to disk — CRITICAL
close(fd);
rename("/tmp/update.bin.tmp", "/opt/firmware/update.bin");  // Atomic on same filesystem
sync();                 // Ensure rename is persisted
```

**Why `fsync` matters**: Vehicles lose power unexpectedly (engine off, battery disconnect). Without `fsync`, data can be in the kernel page cache but not on disk. A power loss at that moment = corrupted update.

---

## 1.2 Networking Fundamentals

Vehicles communicate over cellular (4G/5G), WiFi, and Ethernet. Understanding the network stack is essential.

### The OSI Model — What Matters for OTA

```
Layer 7 — Application    : HTTP/2, gRPC, MQTT (your OTA protocols)
Layer 6 — Presentation   : TLS 1.3 (encryption)
Layer 5 — Session        : TLS session management
Layer 4 — Transport      : TCP (reliable), UDP (for some telemetry)
Layer 3 — Network        : IP routing, VPN tunnels
Layer 2 — Data Link      : Ethernet (in-vehicle), cellular modem
Layer 1 — Physical       : Antenna, wiring harness
```

**For OTA, you primarily work at layers 4-7.**

### TCP vs UDP for OTA

| Property | TCP | UDP |
|----------|-----|-----|
| Reliability | Guaranteed delivery, ordering | Best-effort |
| Overhead | Higher (handshake, ACKs) | Lower |
| Use in OTA | Update package download | Telemetry, heartbeats |

OTA downloads always use TCP (usually HTTP/2 over TLS). You cannot afford missing bytes in a firmware image.

### HTTP/2 — Why It Matters

HTTP/2 is the standard for OTA download connections:

```
HTTP/1.1                          HTTP/2
┌─────────┐                      ┌─────────┐
│ Request  │──────────────>      │ Stream 1 │──>
│ Response │<──────────────      │ Stream 2 │──>  Multiplexed on
│ Request  │──────────────>      │ Stream 3 │──>  a single TCP
│ Response │<──────────────      │ Stream 4 │──>  connection
└─────────┘                      └─────────┘
  Sequential                       Parallel
```

Benefits for OTA:
- **Multiplexing**: Download multiple update packages simultaneously over one connection
- **Header compression (HPACK)**: Less overhead on cellular connections
- **Server push**: Server can proactively send metadata about available updates

### DNS and Service Discovery

Vehicles need to find the OTA backend:

```
Vehicle boots
  → Connects to cellular network
    → DNS query: ota.vehiclecompany.com
      → Returns IP of nearest CDN edge / load balancer
        → TLS handshake with certificate pinning
          → Authenticated connection established
```

**Certificate pinning**: The vehicle only trusts a specific certificate (or CA) for the OTA server. This prevents man-in-the-middle attacks even if a CA is compromised.

---

## 1.3 C/C++ for Embedded Systems

The OTA update agent on the vehicle is almost always written in C or C++. Here's what you need to know.

### Memory Management

In embedded systems, memory is limited and there's no swap space.

```cpp
// BAD — unbounded allocation based on network input
char* buffer = new char[header.content_length];  // What if content_length is 4GB?

// GOOD — bounded allocation with validation
constexpr size_t MAX_CHUNK_SIZE = 1024 * 1024;  // 1MB max
if (header.content_length > MAX_UPDATE_SIZE) {
    return Error::UPDATE_TOO_LARGE;
}
// Download in chunks
auto buffer = std::make_unique<char[]>(MAX_CHUNK_SIZE);
```

### RAII (Resource Acquisition Is Initialization)

Critical pattern for embedded C++. Resources are tied to object lifetime:

```cpp
class PartitionWriter {
    int fd_;
public:
    PartitionWriter(const std::string& path) {
        fd_ = open(path.c_str(), O_WRONLY | O_SYNC);
        if (fd_ < 0) throw std::system_error(errno, std::system_category());
    }

    ~PartitionWriter() {
        if (fd_ >= 0) {
            fsync(fd_);
            close(fd_);
        }
    }

    // No copy, only move
    PartitionWriter(const PartitionWriter&) = delete;
    PartitionWriter& operator=(const PartitionWriter&) = delete;

    ssize_t write(const void* data, size_t len) {
        return ::write(fd_, data, len);
    }
};
```

Why this matters: If an exception occurs mid-update, the destructor ensures the file descriptor is fsynced and closed properly. No resource leaks, no corrupted state.

### Error Handling in Safety-Critical Systems

```cpp
// Use explicit error types, not exceptions (many automotive codebases disable exceptions)
enum class UpdateError {
    SUCCESS = 0,
    DOWNLOAD_FAILED,
    CHECKSUM_MISMATCH,
    PARTITION_WRITE_FAILED,
    SIGNATURE_INVALID,
    ROLLBACK_REQUIRED,
    INSUFFICIENT_SPACE,
    BATTERY_TOO_LOW
};

// Return error codes, log everything
UpdateError applyUpdate(const UpdatePackage& pkg) {
    if (getBatteryLevel() < MIN_BATTERY_FOR_UPDATE) {
        LOG_WARN("Battery too low for update: {}%", getBatteryLevel());
        return UpdateError::BATTERY_TOO_LOW;
    }
    // ...
}
```

---

## 1.4 Python for OTA Tooling

Python is used extensively for OTA tooling, testing, and backend services.

### Common Use Cases

| Use Case | Libraries |
|----------|-----------|
| Build system scripting | `subprocess`, `pathlib`, `click` |
| Package creation | `struct`, `hashlib`, `cryptography` |
| Test automation | `pytest`, `requests`, `paramiko` (SSH to test vehicles) |
| Backend services | `FastAPI`, `Flask`, `celery` |
| Data analysis | `pandas` (update success rates, telemetry) |

### Example: Building an Update Package in Python

```python
import hashlib
import json
import struct
from pathlib import Path
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

def create_update_package(firmware_path: Path, version: str, private_key_path: Path) -> bytes:
    """Create a signed OTA update package."""

    firmware = firmware_path.read_bytes()

    # Compute checksums
    sha256 = hashlib.sha256(firmware).hexdigest()

    # Build metadata
    metadata = {
        "version": version,
        "size": len(firmware),
        "sha256": sha256,
        "target_ecu": "head_unit",
        "compression": "zstd",
        "created_at": datetime.utcnow().isoformat()
    }
    metadata_bytes = json.dumps(metadata).encode()

    # Sign metadata with private key
    private_key = serialization.load_pem_private_key(
        private_key_path.read_bytes(), password=None
    )
    signature = private_key.sign(
        metadata_bytes,
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
        hashes.SHA256()
    )

    # Package format: [metadata_len][metadata][signature_len][signature][firmware]
    package = struct.pack(">I", len(metadata_bytes)) + metadata_bytes
    package += struct.pack(">I", len(signature)) + signature
    package += firmware

    return package
```

---

# Module 2: Embedded Systems & Automotive Architecture

## 2.1 Vehicle Electrical Architecture

A modern vehicle has dozens of computers (ECUs — Electronic Control Units) connected by multiple networks.

```
┌─────────────────────────────────────────────────────────────┐
│                        VEHICLE                               │
│                                                              │
│  ┌──────────┐    Ethernet     ┌──────────────┐              │
│  │ Telematics├───────────────>│  Central      │              │
│  │ Unit (TCU)│    (100Mbps+)  │  Gateway      │              │
│  │ [cellular]│                │               │              │
│  └──────────┘                │               │              │
│                              │               │              │
│  ┌──────────┐    Ethernet    │               │   CAN Bus    │
│  │ Head Unit ├──────────────>│               ├─────────────>│
│  │ (IVI/HU) │               │               │              │
│  │ [display] │               │               │   CAN Bus    │
│  └──────────┘               │               ├─────────────>│
│                              └──────┬───────┘              │
│                                     │                       │
│                              ┌──────┴───────┐              │
│                     ┌────────┤  CAN Buses    ├────────┐    │
│                     │        └──────────────┘         │    │
│                     ▼                                  ▼    │
│              ┌─────────────┐                  ┌──────────┐ │
│              │ Powertrain  │                  │  Body    │ │
│              │ ECUs        │                  │  ECUs    │ │
│              │ - Engine    │                  │ - Lights │ │
│              │ - Transmis. │                  │ - Locks  │ │
│              │ - Battery   │                  │ - HVAC   │ │
│              └─────────────┘                  └──────────┘ │
│                                                             │
│              ┌─────────────┐                  ┌──────────┐ │
│              │ Chassis     │                  │  ADAS    │ │
│              │ ECUs        │                  │  ECUs    │ │
│              │ - ABS       │                  │ - Camera │ │
│              │ - Steering  │                  │ - Radar  │ │
│              │ - Suspension│                  │ - Lidar  │ │
│              └─────────────┘                  └──────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### Key Components

**TCU (Telematics Control Unit):**
- The vehicle's connection to the outside world (cellular modem)
- Downloads OTA update packages from the cloud
- Often the first component to receive and validate updates

**Central Gateway:**
- The "router" of the vehicle
- Controls which messages can pass between network domains
- Enforces security boundaries (e.g., infotainment CAN bus cannot send messages to powertrain CAN bus)
- Routes update packages to the correct ECU

**Head Unit (HU / IVI):**
- The infotainment computer (usually Linux or Android-based)
- Runs the user-facing update UI ("Update available — install now?")
- Often the most powerful computer in the vehicle
- SOTA (Software OTA) updates typically target this

**ECUs:**
- Dozens to hundreds per vehicle
- Range from tiny microcontrollers (8-bit, 64KB flash) to powerful SoCs
- Each runs firmware specific to its function
- FOTA (Firmware OTA) updates target these

## 2.2 In-Vehicle Networks

### CAN Bus (Controller Area Network)

The primary communication protocol inside vehicles since the 1980s.

```
CAN Bus Properties:
- Speed: 500 kbps (CAN 2.0), up to 5 Mbps (CAN FD)
- Topology: Shared bus (all nodes see all messages)
- Message size: 8 bytes (CAN 2.0) or 64 bytes (CAN FD)
- Addressing: Message-based (not node-based) — messages have IDs, not destinations
- Arbitration: Lower ID = higher priority (bit-level arbitration)
```

**CAN Frame Structure:**
```
┌─────┬────┬─────┬──────────┬─────┬─────┬─────┐
│ SOF │ ID │ DLC │   Data   │ CRC │ ACK │ EOF │
│ 1b  │11b │ 4b  │ 0-8 bytes│ 15b │ 2b  │ 7b  │
└─────┴────┴─────┴──────────┴─────┴─────┴─────┘
```

**Why CAN matters for OTA**: To update an ECU's firmware, you send the new firmware image over CAN in small chunks (8 or 64 bytes at a time). This is slow — a 2MB firmware update over CAN 2.0 takes ~30 seconds minimum. CAN FD improved this significantly.

### UDS (Unified Diagnostic Services) — ISO 14229

UDS is the standard protocol for ECU diagnostics and firmware updates, running on top of CAN.

**Key UDS Services for OTA:**

| Service ID | Name | Purpose |
|-----------|------|---------|
| `0x10` | DiagnosticSessionControl | Switch ECU to programming mode |
| `0x11` | ECUReset | Reboot the ECU |
| `0x22` | ReadDataByIdentifier | Read ECU version, hardware info |
| `0x27` | SecurityAccess | Authenticate before flashing |
| `0x31` | RoutineControl | Erase flash memory, verify checksum |
| `0x34` | RequestDownload | Initiate firmware transfer |
| `0x36` | TransferData | Send firmware chunks |
| `0x37` | RequestTransferExit | Finalize transfer |

**Typical UDS Flash Sequence:**
```
Client (Gateway)                    ECU
       │                              │
       │── DiagSessionControl(0x02) ─>│  Enter programming session
       │<── Positive Response ────────│
       │                              │
       │── SecurityAccess(seed req) ─>│  Challenge-response auth
       │<── Seed ─────────────────────│
       │── SecurityAccess(key) ──────>│
       │<── Positive Response ────────│
       │                              │
       │── RoutineControl(erase) ────>│  Erase old firmware
       │<── Positive Response ────────│
       │                              │
       │── RequestDownload ──────────>│  Start transfer
       │<── Positive Response ────────│
       │                              │
       │── TransferData(block 1) ────>│  Send firmware chunks
       │<── Positive Response ────────│
       │── TransferData(block 2) ────>│
       │<── Positive Response ────────│
       │── ...                        │
       │                              │
       │── RequestTransferExit ──────>│  Done transferring
       │<── Positive Response ────────│
       │                              │
       │── RoutineControl(verify) ───>│  Verify checksum
       │<── Positive Response ────────│
       │                              │
       │── ECUReset ─────────────────>│  Reboot with new firmware
       │<── Positive Response ────────│
```

### Automotive Ethernet

Modern vehicles are migrating to Ethernet for high-bandwidth links:

```
CAN Bus: 500 kbps — 5 Mbps
Automotive Ethernet: 100 Mbps — 1 Gbps (100BASE-T1, 1000BASE-T1)
```

This dramatically changes OTA — instead of trickling firmware over CAN at 500kbps, you can send a full Linux rootfs image over Ethernet in seconds.

**SOME/IP (Scalable service-Oriented MiddlewarE over IP):**
- The service-oriented communication protocol for automotive Ethernet
- Replaces CAN's signal-based communication with service-based RPC
- Used for high-bandwidth communication between powerful ECUs

---

# Module 3: OTA Update Systems — Core Concepts

## 3.1 What Is Automotive OTA?

Over-the-Air (OTA) updates allow vehicle manufacturers to remotely update software on vehicles after they've been sold. This is analogous to how your phone gets OS updates, but with much higher stakes.

**Why OTA matters:**
- **Safety recalls**: Fix safety-critical bugs without requiring dealer visits (Tesla has done this extensively)
- **Feature delivery**: Add new features post-purchase (subscription models)
- **Cost reduction**: Eliminates dealer flash campaigns ($100+ per vehicle per visit)
- **Compliance**: Update vehicles to meet new regulations

**What makes automotive OTA hard:**
- **Safety**: A failed update could disable brakes, steering, or airbags
- **Reliability**: Vehicles lose power unexpectedly, have intermittent connectivity
- **Scale**: Millions of vehicles with different hardware configurations
- **Heterogeneity**: A single vehicle has dozens of ECUs from different suppliers with different update mechanisms
- **Bandwidth**: Cellular data is expensive and slow compared to WiFi
- **User consent**: You can't force-reboot someone's car while they're driving

## 3.2 FOTA vs SOTA

```
┌──────────────────────────────────────────────────────────────┐
│                      OTA Updates                              │
│                                                              │
│  ┌─────────────────────┐    ┌─────────────────────────────┐ │
│  │       FOTA           │    │          SOTA                │ │
│  │  Firmware OTA        │    │    Software OTA              │ │
│  │                      │    │                              │ │
│  │  Updates ECU          │    │  Updates applications on     │ │
│  │  firmware (bare-metal │    │  Linux/Android-based         │ │
│  │  or RTOS)            │    │  compute platforms           │ │
│  │                      │    │                              │ │
│  │  Examples:           │    │  Examples:                   │ │
│  │  - Engine controller │    │  - Infotainment apps        │ │
│  │  - ABS module        │    │  - Navigation maps          │ │
│  │  - Battery mgmt (EV) │    │  - Voice assistant          │ │
│  │  - ADAS processor    │    │  - Instrument cluster UI    │ │
│  │                      │    │                              │ │
│  │  Protocol: UDS/CAN   │    │  Protocol: HTTP/gRPC        │ │
│  │  Size: KB to few MB  │    │  Size: MB to GB             │ │
│  │  Risk: HIGH          │    │  Risk: MEDIUM               │ │
│  └─────────────────────┘    └─────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

## 3.3 Update Strategies

### Full Image Update

```
Cloud sends:  [Complete firmware image — e.g., 50MB]
Vehicle:      Writes entire image to inactive partition
              Reboots into new partition
```

- **Pros**: Simple, deterministic — the target state is fully defined
- **Cons**: Large download size, high bandwidth cost over cellular
- **Used for**: Rootfs updates, major version upgrades

### Delta (Differential) Update

```
Cloud computes: diff(v1.2, v1.3) → delta.patch (e.g., 2MB instead of 50MB)
Vehicle:        Applies delta to current image → produces v1.3
                Verifies checksum of result
```

- **Pros**: 90-95% smaller downloads
- **Cons**: Complex — must know exact current version; corruption risks; more CPU-intensive on vehicle
- **Algorithms**: `bsdiff` (classic), `xdelta3`, `zstd` dictionary compression
- **Used for**: Routine updates, bandwidth-constrained deployments

**How bsdiff works (conceptually):**
```
Old file:  [A][B][C][D][E][F][G]
New file:  [A][B][X][D][E][Y][G]

Delta:     Copy 0-2 from old
           Insert X
           Copy 3-5 from old
           Insert Y
           Copy 6-7 from old

Delta size << New file size (because most bytes are shared)
```

### A/B (Dual-Bank) Update

The most common strategy for safety-critical systems:

```
State 1: Running from Bank A (v1.2)
         ┌────────┬────────┐
         │ Bank A │ Bank B │
         │ v1.2   │ (old)  │
         │ ACTIVE │        │
         └────────┴────────┘

State 2: Writing update to Bank B (while vehicle runs normally on Bank A)
         ┌────────┬────────┐
         │ Bank A │ Bank B │
         │ v1.2   │ v1.3   │
         │ ACTIVE │WRITING │
         └────────┴────────┘

State 3: Reboot into Bank B
         ┌────────┬────────┐
         │ Bank A │ Bank B │
         │ v1.2   │ v1.3   │
         │FALLBACK│ ACTIVE │
         └────────┴────────┘

State 4 (if v1.3 fails health check): Automatic rollback to Bank A
         ┌────────┬────────┐
         │ Bank A │ Bank B │
         │ v1.2   │ v1.3   │
         │ ACTIVE │ FAILED │
         └────────┴────────┘
```

**Boot flag mechanism:**
```
# Stored in a dedicated boot config partition (or U-Boot env)
active_bank=B
boot_attempts=0
max_boot_attempts=3
rollback_bank=A

# Bootloader logic (pseudo-code):
if boot_attempts >= max_boot_attempts:
    active_bank = rollback_bank  # Automatic rollback
    boot_attempts = 0
else:
    boot_attempts += 1
    boot(active_bank)

# After successful boot, the OTA agent confirms:
boot_attempts = 0  # "I booted successfully, commit this version"
```

- **Pros**: Near-instant rollback, update happens in background while vehicle runs
- **Cons**: Requires 2x storage space for each updatable component

### In-Place Update (Single Bank)

```
Current: [v1.2]
Update:  Erase → Write v1.3 → Verify → Reboot
```

- **Pros**: Requires less storage
- **Cons**: DANGEROUS — if power is lost during write, the system is bricked. No rollback.
- **Used for**: Very small, resource-constrained ECUs where dual-bank isn't feasible
- **Mitigation**: Use journaling or checkpoint-based writing

## 3.4 Update Campaign Management

An OTA "campaign" is a managed rollout of an update to a fleet of vehicles.

```
┌──────────────────────────────────────────────────────┐
│                  Campaign Manager                     │
│                                                       │
│  Campaign: "ECU-FW-2.1-rollout"                      │
│  ┌─────────────────────────────────────────────┐     │
│  │ Target: All Model X, 2024-2025, NA region   │     │
│  │ Current version: 2.0.x                       │     │
│  │ Target version: 2.1.0                        │     │
│  │ Package: ecu-fw-2.1.0-delta-from-2.0.pkg    │     │
│  │                                               │     │
│  │ Rollout strategy:                             │     │
│  │   Phase 1: 1% of fleet (canary)  ← 48 hours │     │
│  │   Phase 2: 10% of fleet          ← 72 hours │     │
│  │   Phase 3: 50% of fleet          ← 1 week   │     │
│  │   Phase 4: 100% of fleet                     │     │
│  │                                               │     │
│  │ Abort conditions:                             │     │
│  │   - Failure rate > 0.1%                       │     │
│  │   - Any safety-critical error reported        │     │
│  │   - Rollback rate > 1%                        │     │
│  │                                               │     │
│  │ Prerequisites:                                │     │
│  │   - Vehicle parked (not driving)              │     │
│  │   - Battery > 50%                             │     │
│  │   - WiFi connected (preferred) OR cellular    │     │
│  │   - User consent obtained                     │     │
│  └─────────────────────────────────────────────┘     │
└──────────────────────────────────────────────────────┘
```

**Key campaign features:**
- **Staged rollout**: Never push to 100% immediately. Canary → gradual ramp
- **Automatic abort**: If failure metrics exceed thresholds, halt the campaign
- **Targeting**: By VIN, model, year, region, hardware revision, current software version
- **Scheduling**: Updates during off-peak hours, when vehicle is parked
- **Dependency resolution**: ECU A must be updated before ECU B

---

# Module 4: Security in Automotive OTA

## 4.1 Threat Model

```
┌─────────────────────────────────────────────────┐
│               THREAT LANDSCAPE                    │
│                                                   │
│  Cloud Side:                                      │
│  - Compromised build server → malicious firmware │
│  - Compromised CDN → tampered packages           │
│  - Stolen signing keys                           │
│                                                   │
│  Network (in-transit):                           │
│  - Man-in-the-middle on cellular                 │
│  - Rogue WiFi hotspot                            │
│  - DNS spoofing                                  │
│                                                   │
│  Vehicle Side:                                    │
│  - Rollback attack (install older vulnerable fw) │
│  - ECU impersonation on CAN bus                  │
│  - Physical access to debug ports (JTAG, OBD-II)│
│  - Partial update attack (mix old+new components)│
│                                                   │
│  Supply Chain:                                    │
│  - Compromised Tier-1 supplier firmware          │
│  - Backdoored development tools                  │
└─────────────────────────────────────────────────┘
```

## 4.2 Uptane Framework

**Uptane is the industry-standard security framework for automotive OTA.** It was designed by NYU, UMTRI, and SwRI, and is now adopted by most major OEMs.

Uptane extends TUF (The Update Framework) for the automotive context.

### Core Concept: Separation of Trust

Uptane uses multiple servers with separate keys so that compromising one server doesn't compromise the whole system:

```
┌─────────────────┐     ┌──────────────────┐
│  Image Repo      │     │  Director Repo    │
│                  │     │                   │
│  "What updates   │     │  "Which vehicle   │
│   exist"         │     │   gets which      │
│                  │     │   update"          │
│  Signed by:      │     │                   │
│  - Root key      │     │  Signed by:       │
│  - Targets key   │     │  - Root key       │
│  - Snapshot key  │     │  - Targets key    │
│  - Timestamp key │     │  - Snapshot key   │
│                  │     │  - Timestamp key  │
└────────┬────────┘     └────────┬──────────┘
         │                        │
         └───────────┬────────────┘
                     │
                     ▼
              ┌─────────────┐
              │   Vehicle    │
              │              │
              │  Verifies    │
              │  BOTH repos  │
              │  agree on    │
              │  the update  │
              └─────────────┘
```

**Why two repos?**
- If the Image Repo is compromised: attacker can add malicious images, but the Director won't assign them to vehicles
- If the Director is compromised: attacker can try to assign images, but they won't match the Image Repo's signed metadata
- Both must agree for an update to be accepted

### Uptane Metadata Roles

| Role | Purpose | Key Location |
|------|---------|-------------|
| **Root** | Defines which keys are trusted for each role. The trust anchor. | Offline (HSM, air-gapped) |
| **Targets** | Lists available update images with their hashes and sizes | Online (but key can be delegated) |
| **Snapshot** | Provides a consistent view of the Targets metadata at a point in time | Online |
| **Timestamp** | Prevents replay attacks by including an expiration time | Online, rotated frequently |

### Uptane Verification Flow on Vehicle

```
1. Vehicle contacts Director: "I'm VIN 12345, running versions {...}"
2. Director responds with:
   - timestamp.json (signed, with expiration)
   - snapshot.json (signed, references targets)
   - targets.json (signed, lists specific updates for THIS vehicle)

3. Vehicle contacts Image Repo:
   - Gets the same metadata hierarchy
   - Downloads the actual firmware image

4. Vehicle verifies:
   ✓ Timestamp not expired (prevents freeze attack)
   ✓ Snapshot matches timestamp
   ✓ Targets from Director specifies this image for THIS VIN
   ✓ Targets from Image Repo has the same image hash
   ✓ Image hash matches downloaded file
   ✓ Version is NEWER than current (prevents rollback)
   ✓ Hardware ID matches this ECU

5. Only if ALL checks pass → install the update
```

### Rollback Prevention

```
Current version: 2.1.0
Attacker tries to install: 1.9.0 (has known vulnerability)

Vehicle checks:
  targets.json says: minimum_version = 2.0.0
  1.9.0 < 2.0.0 → REJECTED

Even if attacker replays an old targets.json:
  timestamp.json has expiration → old timestamp is expired → REJECTED
```

## 4.3 Code Signing

Every update package must be cryptographically signed. The vehicle verifies the signature before installing.

```
Build Pipeline:
  Source Code → Compile → Link → Binary
                                    │
                                    ▼
                              ┌───────────┐
                              │    HSM     │  Hardware Security Module
                              │            │  (FIPS 140-2 certified)
                              │  Private   │
                              │  Key never │
                              │  leaves    │
                              │  the HSM   │
                              └─────┬─────┘
                                    │
                              Sign(hash(binary))
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │   Signed Package     │
                         │  [metadata]          │
                         │  [signature]         │
                         │  [firmware binary]   │
                         └─────────────────────┘

Vehicle:
  1. Extract metadata + signature
  2. Compute hash of firmware binary
  3. Verify signature using embedded public key
  4. Verify hash matches metadata
  5. Install only if valid
```

**HSM (Hardware Security Module):**
- Dedicated hardware device for key storage and cryptographic operations
- Private keys are generated inside the HSM and never exported
- FIPS 140-2 Level 3+ certification
- Used in the build pipeline (cloud side) and increasingly on vehicles too

### Common Algorithms

| Purpose | Algorithm | Notes |
|---------|-----------|-------|
| Signing | Ed25519 or RSA-4096 with PSS | Ed25519 preferred (faster, smaller keys) |
| Hashing | SHA-256 | For file integrity |
| Encryption | AES-256-GCM | For firmware confidentiality (if needed) |
| Key exchange | ECDH with P-256 | For TLS |
| TLS | TLS 1.3 | For transport security |

## 4.4 Secure Boot Chain

Ensures that only authenticated code runs on the vehicle, from power-on to application layer:

```
┌─────────────────────────────────────────────────┐
│              SECURE BOOT CHAIN                    │
│                                                   │
│  ROM Bootloader (immutable, in silicon)           │
│    │ Verifies signature of...                     │
│    ▼                                              │
│  U-Boot / Secondary Bootloader                    │
│    │ Verifies signature of...                     │
│    ▼                                              │
│  Linux Kernel                                     │
│    │ Verifies signature of...                     │
│    ▼                                              │
│  Root Filesystem (dm-verity)                      │
│    │ Verifies integrity of...                     │
│    ▼                                              │
│  Applications (including OTA agent)               │
│                                                   │
│  If ANY step fails verification → boot halts      │
│  or falls back to recovery partition               │
└─────────────────────────────────────────────────┘
```

**dm-verity**: A Linux kernel feature that provides transparent integrity checking of block devices. The root filesystem is hashed in a Merkle tree; any modification is detected at read time.

---

# Module 5: Backend Infrastructure & Cloud Architecture

## 5.1 OTA Backend Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                        OTA CLOUD BACKEND                          │
│                                                                   │
│  ┌──────────┐  ┌───────────────┐  ┌──────────────┐              │
│  │ API       │  │ Campaign      │  │ Package      │              │
│  │ Gateway   │──│ Manager       │  │ Builder      │              │
│  │ (auth,    │  │               │  │              │              │
│  │  routing) │  │ - Targeting   │  │ - Delta gen  │              │
│  └────┬─────┘  │ - Scheduling  │  │ - Signing    │              │
│       │        │ - Monitoring   │  │ - Validation │              │
│       │        └───────┬───────┘  └──────┬───────┘              │
│       │                │                  │                       │
│       ▼                ▼                  ▼                       │
│  ┌─────────────────────────────────────────────┐                 │
│  │              Message Broker                  │                 │
│  │          (Kafka / RabbitMQ / SQS)            │                 │
│  └──────────────────────┬──────────────────────┘                 │
│                          │                                        │
│       ┌─────────────────┼──────────────────┐                     │
│       ▼                 ▼                  ▼                      │
│  ┌─────────┐    ┌─────────────┐    ┌────────────┐               │
│  │ Vehicle  │    │ Telemetry   │    │ Reporting  │               │
│  │ Registry │    │ Collector   │    │ Service    │               │
│  │          │    │             │    │            │               │
│  │ - VINs   │    │ - Status    │    │ - Success  │               │
│  │ - HW rev │    │ - Errors    │    │   rates    │               │
│  │ - SW ver │    │ - Progress  │    │ - Failures │               │
│  │ - Groups │    │ - Metrics   │    │ - Alerts   │               │
│  └────┬────┘    └──────┬──────┘    └────┬───────┘               │
│       │                │                 │                        │
│       ▼                ▼                 ▼                        │
│  ┌─────────────────────────────────────────────┐                 │
│  │            Database Layer                     │                 │
│  │  PostgreSQL (vehicles, campaigns)             │                 │
│  │  TimescaleDB/InfluxDB (telemetry)            │                 │
│  │  Redis (sessions, rate limiting)              │                 │
│  └─────────────────────────────────────────────┘                 │
│                                                                   │
│  ┌─────────────────────────────────────────────┐                 │
│  │            Storage Layer                      │                 │
│  │  S3 / GCS (update packages, firmware images) │                 │
│  │  CDN (CloudFront / Fastly) for distribution  │                 │
│  └─────────────────────────────────────────────┘                 │
└──────────────────────────────────────────────────────────────────┘
```

## 5.2 Vehicle-to-Cloud Communication Flow

```
Vehicle                                          Cloud
  │                                                │
  │── 1. Check-in (MQTT or HTTPS) ───────────────>│
  │   { vin, hw_rev, sw_versions[], status }       │
  │                                                │
  │<── 2. Update Available ────────────────────────│
  │   { campaign_id, packages[], priority }        │
  │                                                │
  │── 3. Download Request ────────────────────────>│
  │   { package_id, resume_offset }                │
  │                                                │
  │<── 4. Package Download (HTTP/2 + TLS) ────────│
  │   [Streamed from CDN, supports resume]         │
  │                                                │
  │── 5. Download Complete ───────────────────────>│
  │   { package_id, checksum_verified: true }      │
  │                                                │
  │   ... Vehicle waits for safe install window ... │
  │   ... (parked, battery OK, user consent) ...   │
  │                                                │
  │── 6. Install Started ─────────────────────────>│
  │   { package_id, timestamp }                    │
  │                                                │
  │── 7. Install Progress (periodic) ─────────────>│
  │   { progress: 45%, current_ecu: "body_ctrl" }  │
  │                                                │
  │── 8. Install Complete / Failed ───────────────>│
  │   { status: "success", new_versions[] }        │
  │   OR                                           │
  │   { status: "failed", error, rollback: true }  │
  │                                                │
  │── 9. Post-Update Health Report ───────────────>│
  │   { diagnostics[], boot_count, uptime }        │
```

### Resumable Downloads

Vehicles have unreliable connectivity. Downloads must be resumable:

```
GET /packages/fw-2.1.0-delta.pkg HTTP/2
Range: bytes=1048576-    // Resume from 1MB offset
Host: cdn.ota.company.com

HTTP/2 206 Partial Content
Content-Range: bytes 1048576-5242879/5242880
Content-Length: 4194304
```

The vehicle stores download state locally:
```json
{
  "package_id": "fw-2.1.0-delta",
  "total_size": 5242880,
  "downloaded": 1048576,
  "checksum_so_far": "a1b2c3...",
  "temp_path": "/data/ota/downloads/fw-2.1.0-delta.pkg.partial"
}
```

## 5.3 CDN and Distribution

Update packages are large (MB to GB) and distributed to millions of vehicles. A CDN is essential.

```
┌──────────┐     ┌────────────┐
│  Origin   │────>│    CDN     │
│  (S3)     │     │            │
└──────────┘     │  Edge PoPs │
                  │            │
                  │ US-West ●──├──> Vehicles in California
                  │ US-East ●──├──> Vehicles in New York
                  │ EU-West ●──├──> Vehicles in Germany
                  │ AP-SE   ●──├──> Vehicles in Japan
                  └────────────┘
```

**Bandwidth math:**
- 1 million vehicles × 50MB update = 50 PB (petabytes) of transfer
- With delta updates (5MB each) = 5 PB — still massive
- CDN caching is critical; every vehicle downloads the same package

---

# Module 6: Testing & Validation

## 6.1 Testing Pyramid for OTA

```
                    ┌───────────┐
                    │  Fleet    │  Real vehicles in the field
                    │  Canary   │  (1% → 10% → 100%)
                   ─┼───────────┼─
                  / │   HIL     │ \  Hardware-in-the-Loop
                 /  │  Testing  │  \ Real ECUs, simulated vehicle
                /   └───────────┘   \
               /    ┌───────────┐    \
              /     │   SIL     │     \  Software-in-the-Loop
             /      │  Testing  │      \ Simulated ECUs
            /       └───────────┘       \
           /        ┌───────────┐        \
          /         │Integration│         \  End-to-end update flow
         /          │  Tests    │          \ (cloud → vehicle → ECU)
        /           └───────────┘           \
       /            ┌───────────┐            \
      /             │   Unit    │             \  Individual functions
     /              │   Tests   │              \
    /               └───────────┘               \
   ──────────────────────────────────────────────
```

## 6.2 Test Types in Detail

### Unit Tests
```python
# Test delta application logic
def test_apply_delta_produces_correct_output():
    old_firmware = b'\x00\x01\x02\x03\x04'
    delta = generate_delta(old_firmware, b'\x00\x01\xFF\x03\x04')
    result = apply_delta(old_firmware, delta)
    assert result == b'\x00\x01\xFF\x03\x04'

def test_reject_delta_with_wrong_base_version():
    wrong_firmware = b'\xFF\xFF\xFF'
    delta = generate_delta(b'\x00\x01\x02', b'\x00\x01\xFF')
    with pytest.raises(ChecksumMismatchError):
        apply_delta(wrong_firmware, delta)

def test_reject_package_with_invalid_signature():
    package = create_package(firmware, sign_with=WRONG_KEY)
    assert verify_package(package, trusted_keys=REAL_KEYS) is False
```

### Integration Tests
```python
# Test full update flow: cloud → download → install → verify
def test_full_update_flow(mock_vehicle, ota_server):
    # Upload a package to the server
    package = build_test_package(version="2.0.0")
    ota_server.upload(package)

    # Create a campaign targeting the mock vehicle
    campaign = ota_server.create_campaign(
        target_vins=[mock_vehicle.vin],
        package=package
    )

    # Vehicle checks in and discovers update
    mock_vehicle.checkin()
    assert mock_vehicle.pending_updates == [package]

    # Vehicle downloads and installs
    mock_vehicle.download_and_install()

    # Verify version updated
    assert mock_vehicle.current_version == "2.0.0"

    # Verify server recorded success
    assert ota_server.campaign_status(campaign.id).success_count == 1
```

### HIL (Hardware-in-the-Loop) Testing

```
┌──────────────┐     ┌──────────────┐     ┌──────────┐
│ Test          │     │ HIL Rack     │     │ Real     │
│ Controller    │────>│              │────>│ ECU      │
│ (PC running  │     │ CAN/Ethernet │     │ Hardware │
│  test scripts)│     │ Simulator    │     │          │
└──────────────┘     │ Power Supply │     └──────────┘
                      │ GPIO Control │
                      └──────────────┘
```

HIL tests verify:
- Real ECU accepts and installs the update
- ECU boots correctly after update
- ECU functionality works after update
- Power-loss recovery (cut power mid-update, verify ECU recovers)
- Rollback works when update is corrupted

### SIL (Software-in-the-Loop) Testing

Same tests as HIL but with ECU firmware running in an emulator (QEMU, vendor-specific simulators). Faster, cheaper, parallelizable. Used for CI pipelines.

## 6.3 Failure Injection Testing

Deliberately break things to verify recovery:

| Test | What It Simulates | Expected Behavior |
|------|-------------------|-------------------|
| Kill power at 50% flash | Power loss during update | ECU boots from old partition (A/B) or recovery |
| Corrupt downloaded package | Bitrot, network error | Checksum verification fails, re-download |
| Send package signed with wrong key | Compromised server | Signature verification fails, reject |
| Send older version | Rollback attack | Version check fails, reject |
| Drop network mid-download | Cellular dead zone | Resume download when connection returns |
| Fill disk to 99% | Low storage | Update agent reports insufficient space, aborts cleanly |

---

# Module 7: Protocols & Communication

## 7.1 MQTT (Message Queuing Telemetry Transport)

MQTT is the standard for vehicle-to-cloud messaging. Designed for constrained networks.

```
┌─────────┐         ┌──────────┐         ┌─────────┐
│ Vehicle  │────────>│  MQTT    │<────────│  OTA    │
│ (client) │<────────│  Broker  │────────>│ Backend │
│          │  pub/sub│ (HiveMQ, │  pub/sub│         │
└─────────┘         │  Mosquitto│         └─────────┘
                     │  AWS IoT)│
                     └──────────┘
```

**Key MQTT concepts:**

| Concept | Description |
|---------|-------------|
| **Topics** | Hierarchical message channels: `vehicles/{vin}/status`, `vehicles/{vin}/commands/update` |
| **QoS 0** | Fire-and-forget (at most once) — for telemetry |
| **QoS 1** | At least once delivery — for update notifications |
| **QoS 2** | Exactly once delivery — for critical commands |
| **Retained messages** | Broker stores last message; new subscribers get it immediately |
| **Last Will** | Message sent if vehicle disconnects unexpectedly |

**MQTT Topic Design for OTA:**
```
# Vehicle publishes:
vehicles/{vin}/telemetry/status     → { sw_version, battery, signal_strength }
vehicles/{vin}/ota/progress         → { campaign_id, progress_pct, current_ecu }
vehicles/{vin}/ota/result           → { campaign_id, status, error_code }

# Backend publishes (vehicle subscribes):
vehicles/{vin}/ota/commands         → { action: "check_update" }
vehicles/{vin}/ota/campaigns        → { campaign_id, packages[], priority }
fleet/announcements                 → { message: "maintenance window tonight" }
```

**Why MQTT over HTTP for messaging:**
- Persistent connection — no repeated TCP/TLS handshakes
- Bi-directional — server can push to vehicle instantly
- Tiny overhead — 2 byte minimum header vs. HTTP's ~hundreds of bytes
- Built-in keep-alive and reconnection
- Perfect for cellular where every byte and connection counts

## 7.2 gRPC

Used for internal backend service-to-service communication and sometimes for vehicle-to-cloud.

```protobuf
// OTA service definition
service OTAService {
  // Vehicle checks in with current state
  rpc CheckIn(VehicleStatus) returns (UpdateResponse);

  // Stream download progress
  rpc ReportProgress(stream ProgressUpdate) returns (Ack);

  // Download a package (server-side streaming)
  rpc DownloadPackage(DownloadRequest) returns (stream PackageChunk);
}

message VehicleStatus {
  string vin = 1;
  string hardware_revision = 2;
  repeated ECUVersion ecu_versions = 3;
  float battery_level = 4;
  ConnectionType connection = 5;
}

message UpdateResponse {
  repeated UpdatePackage available_updates = 1;
  Priority priority = 2;

  enum Priority {
    ROUTINE = 0;
    IMPORTANT = 1;
    CRITICAL = 2;  // Safety recall
  }
}
```

**gRPC advantages:**
- Binary protocol (protobuf) — smaller payloads than JSON
- Streaming — efficient for large file transfers and real-time progress
- Strong typing — schema enforced at compile time
- Code generation — client/server stubs generated from `.proto` files

## 7.3 CAN / UDS (Recap with Protocol Details)

### CAN Arbitration

When two ECUs transmit simultaneously, the one with the lower ID wins:

```
ECU A transmits ID: 0x100  (binary: 0001 0000 0000)
ECU B transmits ID: 0x200  (binary: 0010 0000 0000)

Bit-by-bit on the bus:
Bit 10:  A sends 0, B sends 0 → bus = 0 (both match)
Bit 9:   A sends 0, B sends 0 → bus = 0 (both match)
Bit 8:   A sends 0, B sends 1 → bus = 0 (dominant wins)
          B detects it lost arbitration → B stops, A continues
```

This means lower ID = higher priority. Safety-critical messages (brakes, steering) get low IDs.

### ISO-TP (ISO 15765-2) — Transport Protocol over CAN

CAN frames are only 8 bytes. Firmware images are megabytes. ISO-TP handles segmentation:

```
Single Frame (≤7 bytes payload):
┌──────┬──────────────┐
│ 0x0N │ Data (N bytes)│  N = 1-7
└──────┴──────────────┘

First Frame (start of multi-frame):
┌──────┬──────┬──────────┐
│ 0x1X │ Size │ Data (6B) │  Announces total size
└──────┴──────┴──────────┘

Consecutive Frame:
┌──────┬──────────────┐
│ 0x2N │ Data (7 bytes)│  N = sequence number (0-F, wraps)
└──────┴──────────────┘

Flow Control:
┌──────┬─────┬──────┬──────┐
│ 0x30 │ Flag│ BSiz │ STmin│  Receiver controls flow
└──────┴─────┴──────┴──────┘
  Flag: 0=Continue, 1=Wait, 2=Overflow
  BSiz: Block size (0=no limit)
  STmin: Minimum separation time between frames
```

---

# Module 8: Build Systems, CI/CD, and Release Engineering

## 8.1 Build Pipeline for Automotive Software

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│  Source   │───>│  Build   │───>│  Test    │───>│  Sign    │
│  (Git)    │    │  (Yocto/ │    │  (Unit,  │    │  (HSM)   │
│           │    │   CMake) │    │   SIL)   │    │          │
└──────────┘    └──────────┘    └──────────┘    └────┬─────┘
                                                      │
┌──────────┐    ┌──────────┐    ┌──────────┐         │
│  Deploy   │<──│  Package │<──│  Delta   │<────────┘
│  (S3/CDN) │    │  (Uptane │    │  Gen     │
│           │    │   meta)  │    │ (bsdiff) │
└──────────┘    └──────────┘    └──────────┘
```

### Yocto Project

Most automotive Linux images are built with Yocto — an embedded Linux build system:

```
Yocto Terminology:
- Recipe (.bb):     Instructions to build one package (like a Makefile)
- Layer:            Collection of recipes (meta-ota, meta-vehicle, meta-bsp)
- BitBake:          The build engine (like Make, but for entire Linux distros)
- Image:            A complete rootfs built from recipes
- Machine:          Target hardware definition (CPU, peripherals)
- Distro:           Distribution configuration (init system, C library, features)
```

**Why Yocto for OTA:**
- Produces reproducible binary images (same source → same output)
- Generates both full images and metadata needed for delta generation
- Integrates with OTA frameworks (meta-updater for Uptane/OSTree)

### OSTree (libostree)

A git-like versioning system for operating system images:

```
OSTree Repository:
  commit abc123 → rootfs snapshot (v2.1.0)
  commit def456 → rootfs snapshot (v2.0.0)
  commit 789abc → rootfs snapshot (v1.9.0)

Update = pull new commit + atomic swap of /sysroot symlink
Rollback = swap symlink back to previous commit

Unlike traditional package managers:
- Atomic: either the whole update applies or nothing changes
- Deduplicated: shared files between versions stored once
- Signed: commits are GPG-signed
```

## 8.2 CI/CD for OTA

```yaml
# Example GitLab CI pipeline for vehicle firmware
stages:
  - build
  - test
  - sign
  - package
  - deploy

build:firmware:
  stage: build
  image: yocto-builder:latest
  script:
    - source oe-init-build-env
    - bitbake vehicle-image
  artifacts:
    paths:
      - build/tmp/deploy/images/

test:unit:
  stage: test
  script:
    - pytest tests/unit/ -v

test:sil:
  stage: test
  script:
    - ./scripts/run_sil_tests.sh
  timeout: 30m

sign:package:
  stage: sign
  script:
    # Sign using HSM (never expose private key)
    - pkcs11-tool --sign --mechanism SHA256-RSA-PKCS-PSS \
        --input-file build/firmware.bin \
        --output-file build/firmware.sig \
        --slot 0 --pin $HSM_PIN
  only:
    - main
    - release/*

package:delta:
  stage: package
  script:
    - python tools/generate_delta.py \
        --old build/firmware-prev.bin \
        --new build/firmware.bin \
        --output build/delta.pkg
    - python tools/create_uptane_metadata.py \
        --package build/delta.pkg \
        --version ${CI_COMMIT_TAG}

deploy:staging:
  stage: deploy
  script:
    - aws s3 cp build/delta.pkg s3://ota-packages/staging/
    - python tools/create_campaign.py --env staging --target canary
  only:
    - release/*
```

---

# Module 9: Industry Standards & Compliance

## 9.1 Key Standards

| Standard | Scope | Relevance to OTA |
|----------|-------|-------------------|
| **ISO 26262** | Functional Safety | Defines ASIL levels (A-D). Safety-critical ECU updates must meet ASIL requirements |
| **ISO/SAE 21434** | Cybersecurity Engineering | Mandates threat analysis and cybersecurity for vehicle lifecycle, including OTA |
| **UNECE WP.29 R155/R156** | Regulations | R155: Cybersecurity management system. R156: Software update management system. **Legally required** in EU, Japan, Korea |
| **Automotive SPICE** | Process Maturity | Assessment model for software development processes. Tier-1 suppliers are audited against this |
| **MISRA C/C++** | Coding Standards | Rules for safe C/C++ code in automotive. Many are enforced by static analysis |
| **AUTOSAR** | Software Architecture | Standardized software platform for ECUs. Defines how update agents integrate |

## 9.2 UNECE R156 — Software Update Management System

**This is a legal requirement.** As of July 2024, all new vehicle types sold in the EU, Japan, and South Korea must comply.

R156 requires the OEM to have:

1. **Software Update Management System (SUMS)**
   - Documented process for managing software updates
   - Risk assessment for each update
   - Traceability from requirement → implementation → test → release

2. **Software identification**
   - Every software component must be uniquely identified (version, hash)
   - Vehicle must be able to report its complete software inventory (SBOM — Software Bill of Materials)

3. **Update integrity and authenticity**
   - Cryptographic verification of all updates
   - Protection against unauthorized modifications

4. **Update documentation**
   - Records of all updates applied to each vehicle
   - Ability to demonstrate compliance during type approval audits

## 9.3 ASIL (Automotive Safety Integrity Level)

From ISO 26262, ASIL classifies the safety risk of a system:

```
ASIL-D: Highest risk (steering, braking)
  → Most rigorous development process
  → Formal verification, extensive testing, redundancy
  → OTA updates require extraordinary validation

ASIL-C: High risk (airbags, stability control)
ASIL-B: Medium risk (headlights, wipers)
ASIL-A: Low risk (interior lighting)
QM:     No safety relevance (infotainment)
  → Standard quality management sufficient
  → OTA updates are more relaxed
```

**What this means for OTA:**
- ASIL-D ECU firmware updates require significantly more testing, review, and approval
- Many OEMs initially only enable OTA for QM and ASIL-A/B components
- The update agent itself may need to meet ASIL requirements if it can affect safety-critical ECUs

---

# Module 10: Putting It All Together

## 10.1 System Design Exercise

**Design an OTA system for a fleet of 500,000 electric vehicles.**

Requirements:
- Each vehicle has 15 ECUs (1 Linux head unit, 14 microcontroller ECUs)
- Head unit has 8GB eMMC storage, cellular + WiFi connectivity
- ECUs range from 256KB to 4MB flash
- Monthly SOTA updates (~200MB), quarterly FOTA updates (~50MB total across ECUs)
- Must comply with UNECE R156 and ISO 21434
- Maximum acceptable update failure rate: 0.01%

**Think through:**

1. **Architecture**: Where does each component live? How do they communicate?
2. **Security**: How do you sign packages? How does the vehicle verify? Key management?
3. **Reliability**: What happens when power is lost? Network drops? Disk fills up?
4. **Scale**: 500K vehicles × 200MB = 100TB per monthly release. CDN strategy?
5. **Rollback**: How do you handle a bad update that passes all tests but fails in the field?
6. **Campaign strategy**: How do you roll out to 500K vehicles safely?

### Reference Architecture Answer

```
                    ┌─────────────────────────────────────┐
                    │           BUILD PIPELINE              │
                    │  Git → Yocto/CMake → Test → Sign     │
                    │  (HSM signing, delta generation)      │
                    └───────────────┬─────────────────────┘
                                    │
                                    ▼
┌───────────────────────────────────────────────────────────┐
│                     OTA CLOUD PLATFORM                     │
│                                                            │
│  ┌──────────┐  ┌───────────┐  ┌──────────┐  ┌─────────┐ │
│  │ Uptane   │  │ Campaign  │  │ Vehicle  │  │Telemetry│ │
│  │ Repos    │  │ Manager   │  │ Registry │  │Collector│ │
│  │(Image +  │  │           │  │          │  │         │ │
│  │ Director)│  │           │  │          │  │         │ │
│  └────┬─────┘  └─────┬─────┘  └────┬─────┘  └────┬────┘ │
│       └───────────────┼─────────────┼─────────────┘      │
│                       ▼             ▼                     │
│              ┌──────────────┐  ┌─────────┐               │
│              │   Database    │  │  Kafka  │               │
│              │  (Postgres)   │  │         │               │
│              └──────────────┘  └─────────┘               │
│                                                            │
│              ┌──────────────────────────┐                 │
│              │    S3 + CloudFront CDN    │                 │
│              │  (package distribution)   │                 │
│              └──────────────────────────┘                 │
└───────────────────────┬───────────────────────────────────┘
                        │ MQTT + HTTPS
                        ▼
┌───────────────────────────────────────────────────────────┐
│                    VEHICLE (Head Unit)                      │
│                                                            │
│  ┌──────────────┐  ┌────────────┐  ┌──────────────────┐  │
│  │ OTA Agent    │  │ Uptane     │  │ Download Manager │  │
│  │ (orchestrate)│  │ Verifier   │  │ (resume, retry)  │  │
│  └──────┬───────┘  └────────────┘  └──────────────────┘  │
│         │                                                  │
│         │  UDS over CAN / Ethernet                        │
│         ▼                                                  │
│  ┌──────────────────────────────────┐                     │
│  │         ECU Update Agent          │                     │
│  │  (flash new firmware via UDS)     │                     │
│  │  A/B partitions where supported   │                     │
│  └──────────────────────────────────┘                     │
└───────────────────────────────────────────────────────────┘
```

---

# Resources & Further Reading

## Official Documentation & Specifications

- **Uptane Standard**: https://uptane.github.io — The definitive resource for automotive OTA security. Read the standard and the deployment best practices guide.
- **The Update Framework (TUF)**: https://theupdateframework.io — The foundation that Uptane builds on. Understand TUF first, then Uptane's automotive extensions.
- **MQTT Specification**: https://mqtt.org — Protocol spec, tutorials, and broker comparisons.
- **Eclipse hawkBit**: https://www.eclipse.org/hawkbit/ — Open-source OTA update management platform. Good reference implementation to study.
- **OSTree (libostree)**: https://ostreedev.github.io/ostree/ — Git-like OS versioning used by many automotive OTA systems.
- **Yocto Project**: https://www.yoctoproject.org — The embedded Linux build system used across the automotive industry.
- **AUTOSAR**: https://www.autosar.org — Standard software architecture for automotive ECUs. Review the Update and Configuration Management (UCM) module.

## Open Source Projects to Study

- **Eclipse Foundation Automotive**: https://www.eclipse.org/org/workinggroups/eclipse_sdv_charter.php — Software Defined Vehicle working group with several OTA-related projects.
- **meta-updater (Yocto layer for OTA)**: Search for "meta-updater" on GitHub — Yocto layer that integrates OSTree + Uptane for building OTA-capable Linux images.
- **GENIVI/COVESA**: https://www.covesa.global — Industry consortium for vehicle software. Publishes reference implementations including OTA.

## Books

- **"Embedded Linux Systems with the Yocto Project"** by Rudolf J. Streif — Comprehensive guide to building embedded Linux with Yocto.
- **"Automotive Ethernet"** by Kirsten Matheus — Deep dive into in-vehicle Ethernet networking.
- **"Introduction to Automotive Cybersecurity"** by Silviu Ciuta — Covers ISO 21434, threat modeling, and secure OTA.

## YouTube & Video Resources

**Note**: YouTube content rotates frequently. Search for these topics on YouTube for current lectures and conference talks:

- Search: **"Uptane automotive OTA security"** — Conference talks from Uptane developers explaining the framework
- Search: **"MQTT tutorial for IoT"** — Many excellent introductory tutorials explaining pub/sub, QoS levels, and broker setup
- Search: **"Yocto Project tutorial embedded Linux"** — Step-by-step guides for building your first embedded Linux image
- Search: **"CAN bus explained automotive"** — Visual explanations of CAN arbitration, framing, and diagnostics
- Search: **"UDS unified diagnostic services tutorial"** — Walkthroughs of the flashing protocol
- Search: **"automotive ethernet SOME/IP"** — Talks from the Automotive Ethernet Congress
- Search: **"ISO 26262 functional safety explained"** — Overviews of ASIL classification and its impact on development
- Search: **"UNECE R155 R156 cybersecurity software update"** — Regulatory requirement explanations

**Channels to follow:**
- **CSS Electronics** — Excellent CAN bus, OBD-II, and automotive data content
- **Phil's Lab** — Embedded systems design and engineering
- **LiveOverflow** — Security-focused, has automotive hacking content

## Courses

- Search on Coursera/Udemy: **"Embedded Linux"**, **"Automotive Cybersecurity"**, **"MQTT for IoT"**
- **Vector Academy** (vector.com) — Professional training for CAN, UDS, AUTOSAR (industry standard tools)

---

## Study Schedule Suggestion

| Week | Focus | Module |
|------|-------|--------|
| 1-2 | Linux systems, networking, C++ refresher | Module 1 |
| 3 | Vehicle architecture, CAN bus, UDS | Module 2 |
| 4-5 | OTA concepts: FOTA/SOTA, A/B updates, campaigns | Module 3 |
| 6 | Security: Uptane, code signing, secure boot | Module 4 |
| 7 | Backend architecture, cloud infrastructure | Module 5 |
| 8 | Testing: unit, integration, HIL, SIL | Module 6 |
| 9 | Protocols: MQTT, gRPC, ISO-TP | Module 7 |
| 10 | CI/CD, Yocto, release engineering | Module 8 |
| 11 | Standards: ISO 26262, R155/R156, AUTOSAR | Module 9 |
| 12 | System design exercise, review | Module 10 |
