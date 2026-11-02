(() => {
  const API_BASE = 'http://127.0.0.1:8788';
  const navItems = document.querySelectorAll('.nav-item');
  const panels = document.querySelectorAll('[data-view-panel]');
  const subtitle = document.getElementById('view-subtitle');
  const themeSwitcher = document.getElementById('theme-switcher');
  const globalDeviceSearch = document.getElementById('global-device-search');
  const globalRefreshBtn = document.getElementById('global-refresh-btn');
  const headerLastUpdated = document.getElementById('header-last-updated');

  const subnetFilter = document.getElementById('subnet-filter');
  const hostFilter = document.getElementById('host-filter');
  const inventoryTableBody = document.getElementById('inventory-table-body');
  const inventoryCount = document.getElementById('inventory-count');
  const detailDeviceTitle = document.getElementById('detail-device-title');
  const detailDeviceSubtitle = document.getElementById('detail-device-subtitle');
  const detailDeviceContent = document.getElementById('detail-device-content');
  const inventorySearch = document.getElementById('inventory-search');
  const detailDeviceSearch = document.getElementById('detail-device-search');
  const detailDeviceMatch = document.getElementById('detail-device-match');
  const detailDeviceOptions = document.getElementById('detail-device-options');
  const detailInterfaceSearch = document.getElementById('detail-interface-search');
  const configDeviceTitle = document.getElementById('config-device-title');
  const configDeviceSubtitle = document.getElementById('config-device-subtitle');
  const configDeviceContent = document.getElementById('config-device-content');
  const configDeviceSearch = document.getElementById('config-device-search');
  const configDeviceSync = document.getElementById('config-device-sync');
  const configDeviceFeedback = document.getElementById('config-device-feedback');
  const dashTotalDevices = document.getElementById('dash-total-devices');
  const dashHealthyDevices = document.getElementById('dash-healthy-devices');
  const dashFailedDevices = document.getElementById('dash-failed-devices');
  const dashVendorCount = document.getElementById('dash-vendor-count');
  const dashVendorBars = document.getElementById('dash-vendor-bars');
  const dashStatusStack = document.getElementById('dash-status-stack');
  const dashRecentDevices = document.getElementById('dash-recent-devices');

  const refreshDataBtn = document.getElementById('fetch-live-ssh-btn');
  const deleteSubnetBtn = document.getElementById('delete-subnet-btn');

  const backendStatus = document.getElementById('backend-status');
  const liveRefreshSummary = document.getElementById('live-refresh-summary');
  const liveRefreshTime = document.getElementById('live-refresh-time');
  const inventoryFeedback = document.getElementById('inventory-feedback');

  const addIpToggle = document.getElementById('add-ip-toggle');
  const addForm = document.getElementById('inventory-add-form');
  const addFormCancel = document.getElementById('add-form-cancel');
  const addSubnet = document.getElementById('add-subnet');
  const addHostStart = document.getElementById('add-host-start');
  const addHostEnd = document.getElementById('add-host-end');

  const configuredSubnets = ['66.162.110.0/24'];
  const subnetUnderTest = '66.162.110.0/24';
  const hostMin = 1;
  const hostMax = 254;

  let inventorySeed = [];
  let selectedDevice = null;
  let interfacePollTimer = null;
  let polledInterfaces = [];
  let interfacePollMeta = { polledAt: '', message: 'Waiting for first poll...' };
  let lldpNeighbors = [];
  let lldpPollMeta = { polledAt: '', message: 'Waiting for LLDP poll...' };
  let inventorySearchTerm = '';
  let detailInterfaceSearchTerm = '';
  let interfaceSortKey = 'name';
  let interfaceSortDirection = 'asc';
  let interfacePage = 1;
  const interfacePageSize = 8;
  let latestHealthMetrics = { cpu: null, memory: null, temperature: null, uptime: '', source: 'derived' };
  let healthTrendSamples = [];
  let operationInProgress = false;
  let activePollDeviceIp = '';
  let activeConfigTab = 'current';
  let activeConfigCurrentView = 'hierarchical';
  let activeConfigFilterView = 'hierarchical';
  let configInterfaceSearchTerm = '';
  let configModePayload = {
    hierarchical: { content: '', source: '', message: '' },
    raw: { content: '', source: '', message: '' },
  };

  const subtitles = {
    dashboard: 'NOC Realtime Overview',
    inventory: 'Inventory Data',
    detail: 'Selected Device Details',
    config: 'Device Configuration Operations'
  };

  const esc = (value) => String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');

  const deriveDeviceStatus = (device) => {
    const stateBlob = `${device?.status || ''} ${device?.netconfState || ''}`.toLowerCase();

    if (
      stateBlob.includes('down')
      || stateBlob.includes('failed')
      || stateBlob.includes('disconnect')
      || stateBlob.includes('error')
      || stateBlob.includes('unreach')
    ) {
      return { label: 'Down', dotClass: 'status-down' };
    }

    if (
      stateBlob.includes('up')
      || stateBlob.includes('discover')
      || stateBlob.includes('connect')
      || stateBlob.includes('ok')
      || stateBlob.includes('success')
    ) {
      return { label: 'Up', dotClass: 'status-up' };
    }

    return { label: 'Down', dotClass: 'status-down' };
  };

  const classifyTopologyRole = (name, model = '', vendor = '') => {
    const key = `${String(name || '').toLowerCase()} ${String(model || '').toLowerCase()} ${String(vendor || '').toLowerCase()}`;
    if (key.includes('fw') || key.includes('firewall') || key.includes('palo') || key.includes('forti') || key.includes('asa')) {
      return 'firewall';
    }
    if (key.includes('cr') || key.includes('ar') || key.includes('er') || key.includes('rtr') || key.includes('router')) {
      return 'router';
    }
    if (key.includes('sw') || key.includes('switch') || key.includes('leaf') || key.includes('tor')) {
      return 'switch';
    }
    return 'unknown';
  };

  const normalizeInterfaceName = (value) => String(value || '').trim().toLowerCase();

  const baseInterfaceName = (value) => {
    const normalized = normalizeInterfaceName(value);
    return normalized.split('.')[0];
  };

  const buildInterfaceStatusLookup = () => {
    const out = new Map();
    polledInterfaces.forEach((itf) => {
      const key = normalizeInterfaceName(itf.name);
      if (!key) {
        return;
      }
      out.set(key, String(itf.oper_status || 'unknown').toLowerCase());

      // Also map base name so xe-0/0/1 and xe-0/0/1.0 can correlate.
      const base = baseInterfaceName(itf.name);
      if (base && !out.has(base)) {
        out.set(base, String(itf.oper_status || 'unknown').toLowerCase());
      }
    });
    return out;
  };

  const resolveInterfaceOperStatus = (lookup, localInterface) => {
    const raw = normalizeInterfaceName(localInterface);
    if (!raw) {
      return 'unknown';
    }

    const direct = lookup.get(raw);
    if (direct) {
      return direct;
    }

    const base = baseInterfaceName(raw);
    const baseHit = lookup.get(base);
    if (baseHit) {
      return baseHit;
    }

    // Final best-effort match for vendor suffix/prefix interface variants.
    for (const [name, status] of lookup.entries()) {
      if (name.startsWith(raw) || raw.startsWith(name) || name.startsWith(base) || base.startsWith(name)) {
        return status;
      }
    }

    return 'unknown';
  };

  const mapStatusTone = (oper) => {
    const value = String(oper || '').toLowerCase();
    if (value === 'up') {
      return 'up';
    }
    if (value === 'down') {
      return 'down';
    }
    return 'unknown';
  };

  const clampPercent = (value, floor, ceil) => {
    const parsed = Number(value);
    if (!Number.isFinite(parsed)) {
      return null;
    }
    return Math.max(floor, Math.min(ceil, Math.round(parsed)));
  };

  const extractHealthMetricsFromPayload = (payload) => {
    const candidateRoots = [payload?.health, payload?.metrics, payload?.system, payload];
    for (const root of candidateRoots) {
      if (!root || typeof root !== 'object') {
        continue;
      }

      const cpu = clampPercent(
        root.cpu ?? root.cpu_usage ?? root.cpu_percent ?? root.cpuUtilization ?? root.cpu_utilization,
        0,
        100,
      );
      const memory = clampPercent(
        root.memory ?? root.memory_usage ?? root.memory_percent ?? root.mem_percent ?? root.memory_utilization,
        0,
        100,
      );
      const temperature = clampPercent(
        root.temperature ?? root.temp ?? root.temperature_c ?? root.temp_celsius,
        0,
        120,
      );
      const uptime = String(root.uptime || root.device_uptime || root.system_uptime || '').trim();

      if (cpu !== null || memory !== null || temperature !== null || uptime) {
        return { cpu, memory, temperature, uptime, source: 'backend' };
      }
    }

    return { cpu: null, memory: null, temperature: null, uptime: '', source: 'derived' };
  };

  const pushHealthSample = (cpuValue) => {
    if (!Number.isFinite(cpuValue)) {
      return;
    }
    const now = Date.now();
    healthTrendSamples.push({ ts: now, value: Math.max(0, Math.min(100, Math.round(cpuValue))) });
    healthTrendSamples = healthTrendSamples.filter((sample) => (now - sample.ts) <= (5 * 60 * 1000));
    if (healthTrendSamples.length > 64) {
      healthTrendSamples = healthTrendSamples.slice(-64);
    }
  };

  const computeHealthSnapshot = () => {
    const total = Math.max(polledInterfaces.length, 1);
    const upCount = polledInterfaces.filter((itf) => String(itf.oper_status || '').toLowerCase() === 'up').length;
    const downCount = polledInterfaces.filter((itf) => String(itf.oper_status || '').toLowerCase() === 'down').length;
    const upPct = Math.round((upCount / total) * 100);

    const derivedCpu = Math.max(18, Math.min(88, Math.round(25 + (100 - upPct) * 0.35 + (lldpNeighbors.length * 2))));
    const derivedMemory = Math.max(22, Math.min(90, Math.round(32 + downCount * 3 + total * 0.08)));
    const derivedTemperature = Math.max(28, Math.min(62, 32 + Math.round(downCount * 1.6 + (100 - upPct) * 0.05)));

    const hasBackendHealthSource = latestHealthMetrics.source === 'backend';
    const cpu = hasBackendHealthSource
      ? (latestHealthMetrics.cpu ?? null)
      : (latestHealthMetrics.cpu ?? derivedCpu);
    const memory = hasBackendHealthSource
      ? (latestHealthMetrics.memory ?? null)
      : (latestHealthMetrics.memory ?? derivedMemory);
    const temperature = hasBackendHealthSource
      ? (latestHealthMetrics.temperature ?? null)
      : (latestHealthMetrics.temperature ?? derivedTemperature);
    const healthState = (memory !== null && memory >= 75) || (cpu !== null && cpu >= 80) ? 'Warning' : 'Normal';

    if (healthTrendSamples.length === 0 && cpu !== null) {
      pushHealthSample(cpu);
    }

    const sampleValues = healthTrendSamples.map((sample) => sample.value);
    const trendSeries = sampleValues.length
      ? (sampleValues.length >= 16
        ? sampleValues.slice(-16)
        : Array.from({ length: 16 - sampleValues.length }, () => sampleValues[0]).concat(sampleValues))
      : Array.from({ length: 16 }, () => 0);

    const trend = trendSeries.map((sample, idx) => {
      const level = Math.max(18, Math.min(92, sample));
      const x = 14 + idx * 20;
      const y = 82 - level * 0.62;
      return `${x},${y.toFixed(1)}`;
    }).join(' ');

    return {
      cpu,
      memory,
      temperature,
      healthState,
      upCount,
      downCount,
      total,
      trend,
      source: latestHealthMetrics.source,
    };
  };

  const getNeighborVendor = (host) => {
    const match = inventorySeed.find((item) => String(item.hostname || '').toLowerCase() === String(host || '').toLowerCase());
    return match?.vendor || '-';
  };

  const normalizeInterfaceIp = (itf) => {
    if (!itf || typeof itf !== 'object') {
      return '-';
    }
    const direct = itf.ip_address || itf.ip || itf.address || itf.primary_ip || itf.ipv4_address;
    if (direct) {
      return String(direct);
    }
    const candidates = [itf.ipv4_addresses, itf.ipv6_addresses, itf.addresses, itf.ips];
    for (const candidate of candidates) {
      if (Array.isArray(candidate) && candidate.length > 0) {
        const first = candidate[0];
        if (typeof first === 'string') {
          return first;
        }
        if (first && typeof first === 'object') {
          const nested = first.ip || first.address || first.addr;
          if (nested) {
            return String(nested);
          }
        }
      }
    }
    return '-';
  };

  const normalizeInterfaceMac = (itf) => {
    if (!itf || typeof itf !== 'object') {
      return '-';
    }
    return String(itf.mac_address || itf.mac || itf.hw_address || itf.hardware_address || '-');
  };

  const renderTopologySvg = () => {
    const centerX = 280;
    const centerY = 130;
    const radius = 90;
    const maxNodes = 10;
    const nodes = lldpNeighbors.slice(0, maxNodes);
    const interfaceStatusLookup = buildInterfaceStatusLookup();
    const centerRole = classifyTopologyRole(selectedDevice?.hostname, selectedDevice?.model, selectedDevice?.vendor);

    const links = nodes.map((neighbor, idx) => {
      const angle = (2 * Math.PI * idx) / Math.max(nodes.length, 1);
      const x = centerX + Math.cos(angle) * radius;
      const y = centerY + Math.sin(angle) * radius;
      const localInterface = neighbor.local_interface || '-';
      const remoteInterface = neighbor.neighbor_interface || '-';
      const localOper = resolveInterfaceOperStatus(interfaceStatusLookup, localInterface);
      const tone = mapStatusTone(localOper);
      return {
        x,
        y,
        name: neighbor.neighbor_hostname || 'unknown-neighbor',
        role: classifyTopologyRole(neighbor.neighbor_hostname),
        localInterface,
        remoteInterface,
        localOper,
        tone,
      };
    });

    const linkLines = links
      .map((link) => {
        const tipX = (centerX + link.x) / 2;
        const tipY = (centerY + link.y) / 2;
        const statusColorClass = `topology-status-${link.tone}`;
        return `
        <g class="topology-link-group">
          <line x1="${centerX}" y1="${centerY}" x2="${link.x}" y2="${link.y}" class="topology-link ${statusColorClass}" />
          <line x1="${centerX}" y1="${centerY}" x2="${link.x}" y2="${link.y}" class="topology-link-hit" />
          <g class="topology-link-tip" transform="translate(${tipX - 84} ${tipY - 38})">
            <rect width="168" height="44" rx="6" class="topology-link-tip-box" />
            <circle cx="10" cy="12" r="4" class="topology-link-tip-dot ${statusColorClass}" />
            <text x="20" y="15" class="topology-link-tip-text">${esc(link.localInterface)} -> ${esc(link.remoteInterface)}</text>
            <text x="8" y="32" class="topology-link-tip-sub">Status: ${esc(link.localOper === 'unknown' ? 'unknown (no interface map)' : link.localOper)}</text>
          </g>
        </g>
      `;
      })
      .join('');

    const neighborNodes = links
      .map((link) => `
        ${link.role === 'firewall'
    ? `<polygon points="${link.x},${link.y - 13} ${link.x + 12},${link.y + 10} ${link.x - 12},${link.y + 10}" class="topology-neighbor-firewall" />`
    : link.role === 'router'
      ? `<polygon points="${link.x - 12},${link.y} ${link.x},${link.y - 12} ${link.x + 12},${link.y} ${link.x},${link.y + 12}" class="topology-neighbor-router" />`
      : `<rect x="${link.x - 11}" y="${link.y - 11}" width="22" height="22" rx="4" class="topology-neighbor-switch" />`}
        <text x="${link.x}" y="${link.y + 4}" text-anchor="middle" class="topology-node-glyph">${link.role === 'firewall' ? 'F' : (link.role === 'router' ? 'R' : 'S')}</text>
        <text x="${link.x}" y="${link.y + 24}" text-anchor="middle" class="topology-node-label">${esc(link.name)}</text>
      `)
      .join('');

    return `
      <svg viewBox="0 0 560 260" class="topology-svg" role="img" aria-label="LLDP topology map">
        ${linkLines}
        ${centerRole === 'firewall'
    ? `<polygon points="${centerX},${centerY - 16} ${centerX + 15},${centerY + 12} ${centerX - 15},${centerY + 12}" class="topology-center-firewall" />`
    : centerRole === 'router'
      ? `<polygon points="${centerX - 16},${centerY} ${centerX},${centerY - 16} ${centerX + 16},${centerY} ${centerX},${centerY + 16}" class="topology-center-router" />`
      : `<rect x="${centerX - 14}" y="${centerY - 14}" width="28" height="28" rx="6" class="topology-center-switch" />`}
        <text x="${centerX}" y="${centerY + 5}" text-anchor="middle" class="topology-node-glyph center">${centerRole === 'firewall' ? 'F' : (centerRole === 'router' ? 'R' : 'S')}</text>
        <text x="${centerX}" y="${centerY + 34}" text-anchor="middle" class="topology-node-label center">${esc(selectedDevice?.hostname || 'device')}</text>
        ${neighborNodes}
      </svg>
    `;
  };

  const renderDetailView = () => {
    if (!detailDeviceContent || !detailDeviceTitle || !detailDeviceSubtitle) {
      return;
    }

    if (!selectedDevice) {
      detailDeviceTitle.textContent = 'Device Detail View';
      detailDeviceSubtitle.textContent = 'Select a hostname from Inventory to load details.';
      detailDeviceContent.innerHTML = '<p class="card-purpose">No device selected.</p>';
      return;
    }

    detailDeviceTitle.textContent = 'Device Detail View';
    detailDeviceSubtitle.textContent = 'Device status and interface data for the selected device.';
    const status = deriveDeviceStatus(selectedDevice);
    const health = computeHealthSnapshot();
    const cpuPct = Number.isFinite(health.cpu) ? health.cpu : null;
    const memPct = Number.isFinite(health.memory) ? health.memory : null;
    const tempC = Number.isFinite(health.temperature) ? health.temperature : null;
    const cpuGaugeColor = cpuPct === null ? '#9aa3ad' : (cpuPct >= 80 ? '#d84f5d' : (cpuPct >= 60 ? '#f7b731' : '#1db954'));
    const memoryGaugeColor = memPct === null ? '#9aa3ad' : (memPct >= 75 ? '#d84f5d' : (memPct >= 60 ? '#f7b731' : '#1db954'));

    const filteredInterfaces = polledInterfaces.filter((itf) => {
      if (!detailInterfaceSearchTerm) {
        return true;
      }
      const blob = `${itf.name || ''} ${itf.description || ''} ${itf.admin_status || ''} ${itf.oper_status || ''} ${normalizeInterfaceIp(itf)} ${normalizeInterfaceMac(itf)}`.toLowerCase();
      return blob.includes(detailInterfaceSearchTerm);
    });

    const readSortValue = (itf, key) => {
      if (key === 'ip_address') {
        return normalizeInterfaceIp(itf);
      }
      if (key === 'mac_address') {
        return normalizeInterfaceMac(itf);
      }
      return String(itf?.[key] || '');
    };

    const sortedInterfaces = [...filteredInterfaces].sort((a, b) => {
      const av = readSortValue(a, interfaceSortKey).toLowerCase();
      const bv = readSortValue(b, interfaceSortKey).toLowerCase();
      if (av < bv) {
        return interfaceSortDirection === 'asc' ? -1 : 1;
      }
      if (av > bv) {
        return interfaceSortDirection === 'asc' ? 1 : -1;
      }
      return 0;
    });

    const totalPages = Math.max(1, Math.ceil(sortedInterfaces.length / interfacePageSize));
    interfacePage = Math.min(interfacePage, totalPages);
    const pageStart = (interfacePage - 1) * interfacePageSize;
    const pagedInterfaces = sortedInterfaces.slice(pageStart, pageStart + interfacePageSize);

    const rows = pagedInterfaces.map((itf) => {
      const oper = String(itf.oper_status || '').toLowerCase();
      const dotClass = oper === 'up' ? 'status-up' : 'status-down';
      const ipAddress = normalizeInterfaceIp(itf);
      const macAddress = normalizeInterfaceMac(itf);
      return `
        <tr>
          <td>${esc(itf.name)}</td>
          <td>${esc(ipAddress)}</td>
          <td>${esc(macAddress)}</td>
          <td><span class="status-dot ${dotClass}"></span>${esc(itf.oper_status)}</td>
          <td>${esc(itf.admin_status)}</td>
          <td>${esc(itf.description)}</td>
        </tr>
      `;
    }).join('');

    const neighborRows = lldpNeighbors.map((neighbor) => `
      <tr>
        <td>${esc(neighbor.local_interface || '-')}</td>
        <td>${esc(neighbor.neighbor_hostname || '-')}</td>
        <td>${esc(getNeighborVendor(neighbor.neighbor_hostname))}</td>
        <td>${esc(neighbor.neighbor_interface || '-')}</td>
        <td>${esc(neighbor.neighbor_mgmt_ip || '-')}</td>
      </tr>
    `).join('');

    const uptimeText = latestHealthMetrics.uptime || 'Waiting for realtime uptime...';

    detailDeviceContent.innerHTML = `
      <div class="detail-breadcrumb">Home > Device Details</div>

      <div class="detail-summary-strip" role="region" aria-label="Selected device summary">
        <div class="summary-main">
          <div class="summary-host">${esc(selectedDevice.hostname || '-')}</div>
          <div class="summary-kind">${esc(selectedDevice.vendor || '-')} ${esc(selectedDevice.model || '')}</div>
        </div>
        <div class="summary-item"><span>Management IP</span><strong>${esc(selectedDevice.mgmtIp || '-')}</strong></div>
        <div class="summary-item"><span>Vendor</span><strong>${esc(selectedDevice.vendor || '-')}</strong></div>
        <div class="summary-item"><span>Model</span><strong>${esc(selectedDevice.model || '-')}</strong></div>
        <div class="summary-item"><span>Serial</span><strong>${esc(selectedDevice.serialNumber || '-')}</strong></div>
        <div class="summary-item status"><span>Status</span><strong><span class="status-dot ${status.dotClass}"></span>${status.label}</strong></div>
      </div>

      <div class="detail-kpi-row">
        <div class="kpi-mini"><span>Total Interfaces</span><strong>${polledInterfaces.length}</strong></div>
        <div class="kpi-mini"><span>Up Interfaces</span><strong>${health.upCount}</strong></div>
        <div class="kpi-mini"><span>Down Interfaces</span><strong>${health.downCount}</strong></div>
        <div class="kpi-mini"><span>CPU Usage</span><strong>${cpuPct === null ? '--' : `${cpuPct}%`}</strong></div>
        <div class="kpi-mini"><span>Memory Usage</span><strong>${memPct === null ? '--' : `${memPct}%`}</strong></div>
        <div class="kpi-mini"><span>LLDP Neighbors</span><strong>${lldpNeighbors.length}</strong></div>
      </div>

      <details class="accordion-card" open>
        <summary class="detail-status-headline">Device Status</summary>
        <div class="detail-status-window" role="region" aria-label="Device status summary">
        <div class="detail-status-grid detail-status-grid-head">
          <span class="detail-status-label">Hostname</span><span class="detail-status-value">${esc(selectedDevice.hostname || '-')}</span>
          <span class="detail-status-label">Management IP</span><span class="detail-status-value">${esc(selectedDevice.mgmtIp || '-')}</span>
          <span class="detail-status-label">Vendor</span><span class="detail-status-value">${esc(selectedDevice.vendor || '-')}</span>
          <span class="detail-status-label">Model</span><span class="detail-status-value">${esc(selectedDevice.model || '-')}</span>
          <span class="detail-status-label">Serial Number</span><span class="detail-status-value">${esc(selectedDevice.serialNumber || '-')}</span>
          <span class="detail-status-label">Location</span><span class="detail-status-value">${esc(selectedDevice.site || 'Bangalore')}</span>
          <span class="detail-status-label">Site</span><span class="detail-status-value">${esc(selectedDevice.site || 'Branch-01')}</span>
          <span class="detail-status-label">Device Type</span><span class="detail-status-value">${esc(selectedDevice.role || 'Router')}</span>
          <span class="detail-status-label">OS Version</span><span class="detail-status-value">${esc(selectedDevice.osVersion || '-')}</span>
          <span class="detail-status-label">Uptime</span><span class="detail-status-value">${esc(uptimeText)}</span>
          <span class="detail-status-label">Last Updated</span><span class="detail-status-value">${esc(interfacePollMeta.polledAt || '--')}</span>
          <span class="detail-status-label">Description</span><span class="detail-status-value">Branch office router</span>
          <span class="detail-status-label">Device Status</span><span class="detail-status-value"><span class="status-dot ${status.dotClass}"></span>${status.label}</span>
        </div>
        </div>
      </details>

      <details class="accordion-card" open>
        <summary class="health-headline">Device Health</summary>
        <div class="health-window" role="region" aria-label="Device health">
        <div class="health-grid">
          <div class="health-card">
            <div class="health-label">CPU Utilization</div>
            <div class="health-gauge" style="--pct:${cpuPct === null ? 0 : cpuPct}; --gauge-color:${cpuGaugeColor};"><span>${cpuPct === null ? '--' : `${cpuPct}%`}</span></div>
            <div class="health-foot ${cpuPct !== null && cpuPct >= 80 ? 'warn' : 'ok'}">${cpuPct === null ? 'Unavailable' : (cpuPct >= 80 ? 'High' : 'Normal')}</div>
          </div>
          <div class="health-card">
            <div class="health-label">Memory Utilization</div>
            <div class="health-gauge" style="--pct:${memPct === null ? 0 : memPct}; --gauge-color:${memoryGaugeColor};"><span>${memPct === null ? '--' : `${memPct}%`}</span></div>
            <div class="health-foot ${memPct !== null && memPct >= 75 ? 'warn' : 'ok'}">${memPct === null ? 'Unavailable' : (memPct >= 75 ? 'Warning' : 'Normal')}</div>
          </div>
          <div class="health-card compact">
            <div class="health-label">Temperature</div>
            <div class="health-temp">${tempC === null ? '--' : `${tempC}&deg;C`}</div>
            <div class="health-foot ${tempC !== null && tempC >= 50 ? 'warn' : 'ok'}">${tempC === null ? 'Unavailable' : (tempC >= 50 ? 'Elevated' : 'Nominal')}</div>
          </div>
          <div class="health-card trend">
            <div class="health-label">CPU Trend (Last 5 mins)</div>
            <svg viewBox="0 0 340 90" class="health-trend" role="img" aria-label="CPU trend">
              <polyline points="${health.trend}" class="trend-line" />
            </svg>
          </div>
        </div>
      </div>
      </details>

      <details class="accordion-card" open>
        <summary class="detail-tab active">Device Interface Details</summary>
      <div class="card-purpose">${esc(interfacePollMeta.message)} | Last poll: ${esc(interfacePollMeta.polledAt || '--')} | Showing ${pagedInterfaces.length}/${filteredInterfaces.length}</div>
      <div class="dropdown-stack">
        <details class="drop" open>
          <summary>
            Interface Details
            <span class="interface-actions-inline">
              <button type="button" class="action-btn" id="interface-export-csv">Export CSV</button>
            </span>
          </summary>
          <div class="drop-body">
            <table class="interface-table">
              <thead>
                <tr>
                  <th data-sort-key="name">Interface Name</th>
                  <th data-sort-key="ip_address">IP Address</th>
                  <th data-sort-key="mac_address">MAC Address</th>
                  <th data-sort-key="oper_status">Operational Status</th>
                  <th data-sort-key="admin_status">Admin Status</th>
                  <th>Description</th>
                </tr>
              </thead>
              <tbody>${rows || '<tr><td colspan="6">No interface data available.</td></tr>'}</tbody>
            </table>
            <div class="interface-pagination">
              <button type="button" class="action-btn" id="interface-prev" ${interfacePage <= 1 ? 'disabled' : ''}>Prev</button>
              <span>Page ${interfacePage} / ${totalPages}</span>
              <button type="button" class="action-btn" id="interface-next" ${interfacePage >= totalPages ? 'disabled' : ''}>Next</button>
            </div>
          </div>
        </details>
      </div>
      </details>

      <details class="accordion-card" open>
        <summary class="topology-headline">Device Topology (LLDP)</summary>
        <div class="topology-window" role="region" aria-label="LLDP topology">
          <div class="topology-headline">LLDP Topology</div>
          <div class="topology-legend" aria-hidden="true">
            <span class="legend-item"><span class="legend-icon legend-router">R</span> Router</span>
            <span class="legend-item"><span class="legend-icon legend-switch">S</span> Switch</span>
            <span class="legend-item"><span class="legend-icon legend-firewall">F</span> Firewall</span>
          </div>
          <div class="card-purpose">${esc(lldpPollMeta.message)} | Last poll: ${esc(lldpPollMeta.polledAt || '--')} | Neighbors: ${lldpNeighbors.length}</div>
          ${renderTopologySvg()}
          <div class="table-wrap topology-table-wrap">
            <table class="inventory-table topology-table">
              <thead>
                <tr>
                  <th>Local Interface</th>
                  <th>Neighbor Hostname</th>
                  <th>Vendor</th>
                  <th>Neighbor Interface</th>
                  <th>Neighbor Mgmt IP</th>
                </tr>
              </thead>
              <tbody>${neighborRows || '<tr><td colspan="5">No LLDP neighbors found.</td></tr>'}</tbody>
            </table>
          </div>
        </div>
      </details>
    `;

    const prevBtn = document.getElementById('interface-prev');
    const nextBtn = document.getElementById('interface-next');
    const exportBtn = document.getElementById('interface-export-csv');
    const sortableHeaders = detailDeviceContent.querySelectorAll('th[data-sort-key]');

    if (prevBtn) {
      prevBtn.addEventListener('click', () => {
        interfacePage = Math.max(1, interfacePage - 1);
        renderDetailView();
      });
    }
    if (nextBtn) {
      nextBtn.addEventListener('click', () => {
        interfacePage = Math.min(totalPages, interfacePage + 1);
        renderDetailView();
      });
    }
    if (exportBtn) {
      exportBtn.addEventListener('click', () => {
        const header = ['Interface Name', 'IP Address', 'MAC Address', 'Operational Status', 'Admin Status', 'Description'];
        const lines = [header.join(',')];
        sortedInterfaces.forEach((itf) => {
          lines.push([
            JSON.stringify(itf.name || ''),
            JSON.stringify(normalizeInterfaceIp(itf)),
            JSON.stringify(normalizeInterfaceMac(itf)),
            JSON.stringify(itf.oper_status || ''),
            JSON.stringify(itf.admin_status || ''),
            JSON.stringify(itf.description || ''),
          ].join(','));
        });
        const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8;' });
        const link = document.createElement('a');
        link.href = URL.createObjectURL(blob);
        link.download = `${selectedDevice?.hostname || 'device'}-interfaces.csv`;
        link.click();
        URL.revokeObjectURL(link.href);
      });
    }

    sortableHeaders.forEach((th) => {
      th.addEventListener('click', () => {
        const key = th.getAttribute('data-sort-key');
        if (!key) {
          return;
        }
        if (interfaceSortKey === key) {
          interfaceSortDirection = interfaceSortDirection === 'asc' ? 'desc' : 'asc';
        } else {
          interfaceSortKey = key;
          interfaceSortDirection = 'asc';
        }
        interfacePage = 1;
        renderDetailView();
      });
    });
  };

  const stopInterfacePolling = () => {
    if (interfacePollTimer) {
      clearInterval(interfacePollTimer);
      interfacePollTimer = null;
    }
  };

  const fetchInterfacesForSelectedDevice = async () => {
    if (!selectedDevice || !selectedDevice.mgmtIp) {
      return;
    }
    const requestIp = selectedDevice.mgmtIp;
    activePollDeviceIp = requestIp;
    try {
      const response = await fetch(`${API_BASE}/api/inventory/device/${encodeURIComponent(requestIp)}/interfaces`);
      if (!response.ok) {
        throw new Error(`Interface fetch failed (${response.status})`);
      }
      const payload = await response.json();
      if (!selectedDevice || selectedDevice.mgmtIp !== requestIp || activePollDeviceIp !== requestIp) {
        return;
      }
      polledInterfaces = Array.isArray(payload.items) ? payload.items : [];
      latestHealthMetrics = extractHealthMetricsFromPayload(payload);

      const total = Math.max(polledInterfaces.length, 1);
      const upCount = polledInterfaces.filter((itf) => String(itf.oper_status || '').toLowerCase() === 'up').length;
      const upPct = Math.round((upCount / total) * 100);
      const fallbackCpu = Math.max(18, Math.min(88, Math.round(25 + (100 - upPct) * 0.35 + (lldpNeighbors.length * 2))));
      pushHealthSample(latestHealthMetrics.cpu ?? fallbackCpu);

      interfacePollMeta = {
        message: payload.message || 'Interface details fetched.',
        polledAt: payload.polled_at ? new Date(payload.polled_at).toLocaleTimeString() : new Date().toLocaleTimeString()
      };

      // Keep interface polling status concise while preserving health notes for debugging.
      if (payload.health_message && !payload.health) {
        interfacePollMeta.message = `${interfacePollMeta.message} Health data unavailable.`;
      }
      renderDetailView();
    } catch (error) {
      if (!selectedDevice || selectedDevice.mgmtIp !== requestIp || activePollDeviceIp !== requestIp) {
        return;
      }
      interfacePollMeta = {
        message: String(error.message || 'Failed to poll interfaces.'),
        polledAt: new Date().toLocaleTimeString()
      };
      polledInterfaces = [];
      latestHealthMetrics = { cpu: null, memory: null, temperature: null, uptime: '', source: 'derived' };
      pushHealthSample(26);
      renderDetailView();
    }
  };

  const fetchLldpTopologyForSelectedDevice = async () => {
    if (!selectedDevice || !selectedDevice.mgmtIp) {
      return;
    }
    const requestIp = selectedDevice.mgmtIp;
    try {
      const response = await fetch(`${API_BASE}/api/inventory/device/${encodeURIComponent(requestIp)}/topology/lldp`);
      if (!response.ok) {
        throw new Error(`LLDP fetch failed (${response.status})`);
      }
      const payload = await response.json();
      if (!selectedDevice || selectedDevice.mgmtIp !== requestIp) {
        return;
      }
      lldpNeighbors = Array.isArray(payload.items) ? payload.items : [];
      lldpPollMeta = {
        message: payload.message || 'LLDP topology fetched.',
        polledAt: payload.polled_at ? new Date(payload.polled_at).toLocaleTimeString() : new Date().toLocaleTimeString()
      };
      renderDetailView();
    } catch (error) {
      if (!selectedDevice || selectedDevice.mgmtIp !== requestIp) {
        return;
      }
      lldpNeighbors = [];
      lldpPollMeta = {
        message: String(error.message || 'Failed to poll LLDP topology.'),
        polledAt: new Date().toLocaleTimeString()
      };
      renderDetailView();
    }
  };

  const startInterfacePolling = () => {
    stopInterfacePolling();
    if (!selectedDevice) {
      return;
    }
    fetchInterfacesForSelectedDevice();
    fetchLldpTopologyForSelectedDevice();
    interfacePollTimer = window.setInterval(() => {
      fetchInterfacesForSelectedDevice();
      fetchLldpTopologyForSelectedDevice();
    }, 15000);
  };

  const syncDetailDeviceOptions = () => {
    if (!detailDeviceOptions) {
      return;
    }
    detailDeviceOptions.innerHTML = '';
    inventorySeed
      .filter((item) => String(item.hostname || '').trim() !== '')
      .forEach((item) => {
        const option = document.createElement('option');
        option.value = `${item.hostname} (${item.mgmtIp})`;
        detailDeviceOptions.appendChild(option);
      });
    updateDetailDeviceMatchBadge();
  };

  const setDetailDeviceMatchBadge = (text, tone = 'neutral') => {
    if (!detailDeviceMatch) {
      return;
    }
    detailDeviceMatch.classList.remove('neutral', 'ok', 'warn', 'error');
    detailDeviceMatch.classList.add(tone);
    detailDeviceMatch.textContent = text;
  };

  const findDeviceMatches = (rawQuery) => {
    const query = String(rawQuery || '').trim().toLowerCase();
    if (!query) {
      return [];
    }

    return inventorySeed.filter((item) => {
      const host = String(item.hostname || '').toLowerCase();
      const ip = String(item.mgmtIp || '').toLowerCase();
      const combined = `${host} (${ip})`;
      return host.includes(query) || ip.includes(query) || combined.includes(query);
    });
  };

  const findBestDeviceMatch = (rawQuery, options = {}) => {
    const requireDiscovered = Boolean(options.requireDiscovered);
    const query = String(rawQuery || '').trim().toLowerCase();
    if (!query) {
      return null;
    }

    const candidates = requireDiscovered
      ? inventorySeed.filter((item) => String(item.status || '') === 'Discovered')
      : inventorySeed;

    const exact = candidates.find((item) => {
      const host = String(item.hostname || '').toLowerCase();
      const ip = String(item.mgmtIp || '').toLowerCase();
      const combined = `${host} (${ip})`;
      return host === query || ip === query || combined === query;
    });
    if (exact) {
      return exact;
    }

    const isIpLike = /^\d+\.\d+\.\d+\.\d+$/.test(query);
    if (isIpLike) {
      return null;
    }

    const matches = candidates.filter((item) => {
      const host = String(item.hostname || '').toLowerCase();
      const ip = String(item.mgmtIp || '').toLowerCase();
      const combined = `${host} (${ip})`;
      return host.includes(query) || ip.includes(query) || combined.includes(query);
    });
    return matches[0] || null;
  };

  const updateDetailDeviceMatchBadge = () => {
    if (!detailDeviceSearch) {
      return;
    }

    const query = String(detailDeviceSearch.value || '').trim();
    if (!query) {
      setDetailDeviceMatchBadge('Live Match: --', 'neutral');
      return;
    }

    const matches = findDeviceMatches(query);
    if (matches.length === 0) {
      setDetailDeviceMatchBadge('Live Match: 0', 'error');
      return;
    }
    if (matches.length === 1) {
      setDetailDeviceMatchBadge('Live Match: 1', 'ok');
      return;
    }
    setDetailDeviceMatchBadge(`Live Match: ${matches.length}`, 'warn');
  };

  const setSelectedDevice = (device, reason = 'Polling interfaces...') => {
    selectedDevice = device;
    activePollDeviceIp = device?.mgmtIp || '';
    resetConfigModePayload();
    polledInterfaces = [];
    latestHealthMetrics = { cpu: null, memory: null, temperature: null, uptime: '', source: 'derived' };
    healthTrendSamples = [];
    interfacePollMeta = { polledAt: '', message: reason };
    lldpNeighbors = [];
    lldpPollMeta = { polledAt: '', message: `Polling LLDP topology for ${device?.hostname || 'device'}...` };
    renderDetailView();
    renderDeviceConfigView();
    startInterfacePolling();
  };

  const selectDeviceFromDetailSearch = () => {
    if (!detailDeviceSearch) {
      return;
    }
    const query = String(detailDeviceSearch.value || '').trim().toLowerCase();
    if (!query) {
      updateDetailDeviceMatchBadge();
      return;
    }
    const matches = findDeviceMatches(query);
    const found = matches[0] || null;

    if (!found) {
      interfacePollMeta = { polledAt: '', message: `No device match for "${query}".` };
      selectedDevice = null;
      polledInterfaces = [];
      renderDetailView();
      renderDeviceConfigView();
      updateDetailDeviceMatchBadge();
      return;
    }

    setSelectedDevice(found, `Polling interfaces for ${found.hostname}...`);
    updateDetailDeviceMatchBadge();
  };

  const autoSelectDeviceFromDetailSearch = () => {
    if (!detailDeviceSearch) {
      return;
    }
    const queryRaw = String(detailDeviceSearch.value || '').trim();
    if (!queryRaw) {
      updateDetailDeviceMatchBadge();
      return;
    }

    const query = queryRaw.toLowerCase();
    const matches = findDeviceMatches(query);
    if (matches.length === 0) {
      updateDetailDeviceMatchBadge();
      return;
    }

    const exact = matches.find((item) => {
      const host = String(item.hostname || '').toLowerCase();
      const ip = String(item.mgmtIp || '').toLowerCase();
      const combined = `${host} (${ip})`;
      return host === query || ip === query || combined === query;
    });

    if (exact) {
      setSelectedDevice(exact, `Polling interfaces for ${exact.hostname}...`);
      updateDetailDeviceMatchBadge();
      return;
    }

    if (matches.length === 1) {
      const only = matches[0];
      setSelectedDevice(only, `Polling interfaces for ${only.hostname}...`);
    }
    updateDetailDeviceMatchBadge();
  };

  const setFeedback = (message, kind = '') => {
    if (!inventoryFeedback) {
      return;
    }
    inventoryFeedback.textContent = message;
    inventoryFeedback.classList.remove('error', 'success');
    if (kind) {
      inventoryFeedback.classList.add(kind);
    }
  };

  const setBackendStatus = (state, detail = '') => {
    if (!backendStatus) {
      return;
    }
    backendStatus.classList.remove('connected', 'disconnected', 'unknown');
    if (state === 'connected') {
      backendStatus.classList.add('connected');
      backendStatus.textContent = 'Backend: Connected';
      return;
    }
    if (state === 'disconnected') {
      backendStatus.classList.add('disconnected');
      backendStatus.textContent = detail ? `Backend: Disconnected (${detail})` : 'Backend: Disconnected';
      return;
    }
    backendStatus.classList.add('unknown');
    backendStatus.textContent = 'Backend: Checking...';
  };

  const setLiveRefreshMeta = (summaryText = 'Live: --', timestampText = 'Last refresh: --') => {
    if (liveRefreshSummary) {
      liveRefreshSummary.textContent = summaryText;
    }
    if (liveRefreshTime) {
      liveRefreshTime.textContent = timestampText;
    }
  };

  const setConfigFeedback = (message = '', kind = '') => {
    if (!configDeviceFeedback) {
      return;
    }
    configDeviceFeedback.textContent = message;
    configDeviceFeedback.className = 'config-device-feedback';
    if (kind) {
      configDeviceFeedback.classList.add(kind);
    }
  };

  const resetConfigModePayload = () => {
    configModePayload = {
      hierarchical: { content: '', source: '', message: '' },
      raw: { content: '', source: '', message: '' },
    };
  };

  const fetchCurrentConfigForMode = async (mode, force = false) => {
    if (!selectedDevice || !selectedDevice.mgmtIp) {
      return '';
    }
    if (!force && configModePayload[mode] && configModePayload[mode].content) {
      return configModePayload[mode].content;
    }
    try {
      const response = await fetch(`${API_BASE}/api/device-config/${encodeURIComponent(selectedDevice.mgmtIp)}/current?mode=${encodeURIComponent(mode)}`);
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail || `Failed to fetch ${mode} config`);
      }
      configModePayload[mode] = {
        content: String(payload.content || ''),
        source: String(payload.source || ''),
        message: String(payload.message || ''),
      };
      return configModePayload[mode].content;
    } catch (error) {
      setConfigFeedback(String(error.message || `Failed to fetch ${mode} config.`), 'error');
      return '';
    }
  };

  const buildHierarchicalConfigBlocks = (device) => {
    const discoveredInterfaces = polledInterfaces.length;
    const upInterfaces = polledInterfaces.filter((itf) => /up/i.test(String(itf.operStatus || ''))).length;
    const downInterfaces = Math.max(discoveredInterfaces - upInterfaces, 0);
    const keyVlans = polledInterfaces
      .map((itf) => String(itf.vlan || '').trim())
      .filter((value) => value && value !== '-')
      .slice(0, 5);

    return [
      { title: 'System', lines: [`Hostname: ${device.hostname || '-'}`, `Vendor: ${device.vendor || '-'}`, `Model: ${device.model || '-'}`, `OS Version: ${device.osVersion || '-'}`] },
      { title: 'Management', lines: [`Mgmt IP: ${device.mgmtIp || '-'}`, `Site: ${device.site || '-'}`, `Role: ${device.role || '-'}`] },
      { title: 'Interfaces', lines: [`Discovered: ${discoveredInterfaces}`, `Up: ${upInterfaces}`, `Down: ${downInterfaces}`, `Sample VLANs: ${keyVlans.length ? keyVlans.join(', ') : 'N/A'}`] },
      { title: 'Health', lines: [`CPU: ${latestHealthMetrics.cpu === null ? '--' : `${latestHealthMetrics.cpu}%`}`, `Memory: ${latestHealthMetrics.memory === null ? '--' : `${latestHealthMetrics.memory}%`}`, `Uptime: ${latestHealthMetrics.uptime || '--'}`] },
    ];
  };

  const buildRawConfigText = (device) => {
    const lines = [
      `! Device: ${device.hostname || 'unselected-device'}`,
      `! Mgmt IP: ${device.mgmtIp || '-'}`,
      `! Vendor: ${device.vendor || '-'}`,
      `! Model: ${device.model || '-'}`,
      `! Last Poll: ${interfacePollMeta.polledAt || '--'}`,
      '!',
      `hostname ${device.hostname || 'device'}`,
      '!',
    ];

    if (polledInterfaces.length === 0) {
      lines.push('! No live interface data available for this device.');
      return lines.join('\n');
    }

    polledInterfaces.slice(0, 20).forEach((itf) => {
      lines.push(`interface ${itf.name || 'unknown'}`);
      lines.push(` description ${itf.description || '-'}`);
      lines.push(` oper-status ${itf.operStatus || '-'}`);
      lines.push(` admin-status ${itf.adminStatus || '-'}`);
      lines.push(` speed ${itf.speed || '-'}`);
      lines.push(` duplex ${itf.duplex || '-'}`);
      if (itf.ipv4) {
        lines.push(` ip address ${itf.ipv4}`);
      }
      lines.push('!');
    });

    return lines.join('\n');
  };

  const buildInterfaceFilteredConfig = (configText, interfaceQuery) => {
    const source = String(configText || '');
    const query = String(interfaceQuery || '').trim().toLowerCase();
    if (!source) {
      return '';
    }
    if (!query) {
      return 'Type an interface in search (examples: ge-0/0/0, xe-0/0/1, GigabitEthernet0/1) to view interface-only config.';
    }

    const lines = source.split('\n');
    const outputBlocks = [];

    // 1) Cisco/Juniper style "interface <name>" blocks.
    for (let i = 0; i < lines.length; i += 1) {
      const line = lines[i];
      if (!/^\s*interface\s+/i.test(line)) {
        continue;
      }
      const normalized = line.toLowerCase();
      if (!normalized.includes(query)) {
        continue;
      }

      const block = [line];
      for (let j = i + 1; j < lines.length; j += 1) {
        const next = lines[j];
        if (/^\s*interface\s+/i.test(next) || /^\s*!\s*$/i.test(next)) {
          break;
        }
        block.push(next);
      }
      outputBlocks.push(block.join('\n'));
    }

    // 2) "set interfaces <name> ..." style lines.
    const setLines = lines.filter((line) => {
      const normalized = line.toLowerCase();
      return normalized.includes('set interfaces') && normalized.includes(query);
    });
    if (setLines.length > 0) {
      outputBlocks.push(setLines.join('\n'));
    }

    // 3) Fallback: matching lines with compact surrounding context.
    if (outputBlocks.length === 0) {
      const context = [];
      for (let i = 0; i < lines.length; i += 1) {
        if (!lines[i].toLowerCase().includes(query)) {
          continue;
        }
        const start = Math.max(0, i - 2);
        const end = Math.min(lines.length - 1, i + 2);
        context.push(lines.slice(start, end + 1).join('\n'));
      }
      if (context.length > 0) {
        outputBlocks.push(context.join('\n\n'));
      }
    }

    return outputBlocks.length > 0
      ? outputBlocks.join('\n\n! ---- interface block separator ----\n\n')
      : `No interface-specific config found for "${interfaceQuery}".`;
  };

  const applyTheme = (theme) => {
    const selected = theme === 'dark' ? 'dark' : 'light';
    document.body.classList.toggle('theme-dark', selected === 'dark');
    document.body.classList.toggle('theme-light', selected === 'light');
    if (themeSwitcher) {
      themeSwitcher.value = selected;
    }
    try {
      localStorage.setItem('nms-theme', selected);
    } catch (err) {
      // Ignore storage errors.
    }
  };

  const looksLikeIpv4 = (value) => /^\d+\.\d+\.\d+\.\d+$/.test(String(value || '').trim());

  const normalizeHostname = (rawHostname, mgmtIp) => {
    const host = String(rawHostname || '').trim();
    const ip = String(mgmtIp || '').trim();
    const low = host.toLowerCase();
    if (!host || ['unknown', 'n/a', 'na', 'none', 'null', 'localhost'].includes(low)) {
      return ip || '';
    }
    // If backend returns IP as hostname, keep UI stable with IP fallback.
    if (looksLikeIpv4(host) && (!ip || host === ip)) {
      return ip || host;
    }
    return host;
  };

  const mapInventoryItems = (items) => (items || []).map((item) => {
    const mgmtIp = item.mgmt_ip || item.mgmtIp || item.ip || item.management_ip || '';
    const hostname = normalizeHostname(
      item.hostname || item.host_name || item.device_hostname || item.name || '',
      mgmtIp,
    );

    return {
      hostname,
      mgmtIp,
      vendor: item.vendor,
      model: item.model,
      osVersion: item.os_version || item.osVersion,
      serialNumber: item.serial_number || item.serialNumber,
      site: item.site,
      role: item.role,
      status: item.status,
      netconfState: item.netconf
    };
  });

  const renderDashboard = () => {
    if (!dashTotalDevices || !dashHealthyDevices || !dashFailedDevices || !dashVendorCount) {
      return;
    }

    const total = inventorySeed.length;
    const discovered = inventorySeed.filter((item) => String(item.status || '') === 'Discovered').length;
    const failed = inventorySeed.filter((item) => String(item.status || '') === 'Fetch Failed').length;
    const pending = inventorySeed.filter((item) => String(item.status || '') === 'Pending Discovery').length;

    dashTotalDevices.textContent = String(total);
    dashHealthyDevices.textContent = String(discovered);
    dashFailedDevices.textContent = String(failed);

    const vendorMap = new Map();
    inventorySeed.forEach((item) => {
      const vendor = String(item.vendor || 'Unknown').trim() || 'Unknown';
      vendorMap.set(vendor, (vendorMap.get(vendor) || 0) + 1);
    });
    dashVendorCount.textContent = String(vendorMap.size);

    if (dashVendorBars) {
      const vendorRows = Array.from(vendorMap.entries()).sort((a, b) => b[1] - a[1]).slice(0, 6);
      const maxVendor = Math.max(...vendorRows.map((entry) => entry[1]), 1);
      dashVendorBars.innerHTML = vendorRows.length
        ? vendorRows.map(([vendor, count]) => {
          const width = Math.max(8, Math.round((count / maxVendor) * 100));
          return `
            <div class="vendor-row">
              <span class="vendor-name">${esc(vendor)}</span>
              <div class="vendor-meter"><i style="width:${width}%"></i></div>
              <span class="vendor-count">${count}</span>
            </div>
          `;
        }).join('')
        : '<p class="card-purpose">No vendor distribution available.</p>';
    }

    if (dashStatusStack) {
      const statusRows = [
        { label: 'Discovered', value: discovered, className: 'ok' },
        { label: 'Fetch Failed', value: failed, className: 'error' },
        { label: 'Pending', value: pending, className: 'pending' },
      ];
      const maxStatus = Math.max(...statusRows.map((row) => row.value), 1);
      dashStatusStack.innerHTML = statusRows.map((row) => {
        const width = Math.max(8, Math.round((row.value / maxStatus) * 100));
        return `
          <div class="status-row ${row.className}">
            <span>${row.label}</span>
            <div class="status-meter"><i style="width:${width}%"></i></div>
            <strong>${row.value}</strong>
          </div>
        `;
      }).join('');
    }

    if (dashRecentDevices) {
      const recent = [...inventorySeed]
        .filter((item) => String(item.hostname || '').trim())
        .slice(-6)
        .reverse();

      dashRecentDevices.innerHTML = recent.length
        ? recent.map((item) => `
          <li>
            <span class="device-name">${esc(item.hostname)}</span>
            <span class="device-meta">${esc(item.mgmtIp)} | ${esc(item.vendor || 'Unknown')} | ${esc(item.status || 'Unknown')}</span>
          </li>
        `).join('')
        : '<li>No devices discovered yet.</li>';
    }
  };

  const renderDeviceConfigView = () => {
    if (!configDeviceContent || !configDeviceTitle || !configDeviceSubtitle) {
      return;
    }

    const hasSelectedDevice = Boolean(selectedDevice);
    const device = selectedDevice || {};
    const status = hasSelectedDevice
      ? deriveDeviceStatus(device)
      : { label: 'No Device Selected', dotClass: 'status-unknown' };
    configDeviceTitle.textContent = hasSelectedDevice
      ? `${device.hostname || device.mgmtIp} - Device Config`
      : 'Device Configuration Dashboard';
    configDeviceSubtitle.textContent = hasSelectedDevice
      ? 'Configuration lifecycle, backup, compare, compliance and deployment controls.'
      : 'Select a device from Inventory or Device Details to apply configuration actions.';

    const hierarchicalConfig = hasSelectedDevice ? (configModePayload.hierarchical.content || '') : '';
    const rawConfig = hasSelectedDevice ? (configModePayload.raw.content || '') : '';
    const roleBlob = `${String(device.role || '').toLowerCase()} ${String(device.model || '').toLowerCase()}`;
    const isSwitch = roleBlob.includes('switch') || roleBlob.includes('sw');
    const isFirewall = roleBlob.includes('firewall') || roleBlob.includes('fw');
    const glyph = isFirewall ? 'FW' : (isSwitch ? 'SW' : 'RT');
    const glyphClass = isFirewall ? 'firewall' : (isSwitch ? 'switch' : 'router');
    const leftMode = activeConfigCurrentView;
    const rightMode = activeConfigFilterView;
    const leftConfigText = leftMode === 'raw' ? rawConfig : hierarchicalConfig;
    const rightSourceText = rightMode === 'raw' ? rawConfig : hierarchicalConfig;
    const rightConfigText = buildInterfaceFilteredConfig(rightSourceText, configInterfaceSearchTerm);
    const terminalPreview = (rawConfig || hierarchicalConfig || '').split('\n').slice(0, 10).join('\n');
    const backupRows = [
      { dt: '18 Oct 2024 10:00', type: 'Running Config', size: '45 KB' },
      { dt: '17 Oct 2024 10:00', type: 'Startup Config', size: '44 KB' },
      { dt: '16 Oct 2024 10:00', type: 'Running Config', size: '45 KB' },
      { dt: '15 Oct 2024 10:00', type: 'Running Config', size: '45 KB' },
      { dt: '14 Oct 2024 10:00', type: 'Startup Config', size: '44 KB' },
    ];

    configDeviceContent.innerHTML = `
      <div class="config-summary-card">
        <div class="config-summary-strip">
          <div class="summary-device-block">
            <div class="device-thumb ${glyphClass}">${glyph}</div>
            <div class="summary-device-text">
              <strong>${esc(device.hostname || '-')}</strong>
              <span>${esc(device.vendor || '-')} ${esc(device.model || '')} | ${esc(device.role || 'Network Device')}</span>
            </div>
          </div>
          <div class="summary-strip-item"><label>Management IP</label><strong>${esc(device.mgmtIp || '-')}</strong></div>
          <div class="summary-strip-item"><label>Vendor</label><strong>${esc(device.vendor || '-')}</strong></div>
          <div class="summary-strip-item"><label>Model</label><strong>${esc(device.model || '-')}</strong></div>
          <div class="summary-strip-item"><label>Serial</label><strong>${esc(device.serialNumber || '-')}</strong></div>
          <div class="config-health-chip ${status.dotClass}">
            <span class="status-dot ${status.dotClass}"></span>${status.label}
          </div>
        </div>
        <div class="config-summary-grid">
          <div><label>Site</label><span>${esc(device.site || '-')}</span></div>
          <div><label>OS Version</label><span>${esc(device.osVersion || '-')}</span></div>
          <div><label>Role</label><span>${esc(device.role || '-')}</span></div>
          <div><label>Config Source</label><span>${esc(leftMode === 'raw' ? 'CLI set output' : 'Hierarchical output')}</span></div>
        </div>
      </div>

      ${hasSelectedDevice ? '' : '<p class="card-purpose">No device selected. Use the Device search above, then press Enter or open a device from Inventory.</p>'}

      <div class="config-tabbar" role="tablist" aria-label="Device config modules">
        <button class="config-tab ${activeConfigTab === 'current' ? 'active' : ''}" type="button" data-config-tab="current">Current Config</button>
        <button class="config-tab ${activeConfigTab === 'backup' ? 'active' : ''}" type="button" data-config-tab="backup">Backup Config</button>
        <button class="config-tab ${activeConfigTab === 'terminal' ? 'active' : ''}" type="button" data-config-tab="terminal">SSH Terminal</button>
        <button class="config-tab ${activeConfigTab === 'compare' ? 'active' : ''}" type="button" data-config-tab="compare">Config Compare</button>
        <button class="config-tab ${activeConfigTab === 'history' ? 'active' : ''}" type="button" data-config-tab="history">Config History</button>
        <button class="config-tab ${activeConfigTab === 'templates' ? 'active' : ''}" type="button" data-config-tab="templates">Templates</button>
        <button class="config-tab ${activeConfigTab === 'schedule' ? 'active' : ''}" type="button" data-config-tab="schedule">Scheduled Backup</button>
        <button class="config-tab ${activeConfigTab === 'deploy' ? 'active' : ''}" type="button" data-config-tab="deploy">Deploy Config</button>
        <button class="config-tab ${activeConfigTab === 'compliance' ? 'active' : ''}" type="button" data-config-tab="compliance">Compliance</button>
        <button class="config-tab ${activeConfigTab === 'facts' ? 'active' : ''}" type="button" data-config-tab="facts">Device Facts</button>
      </div>

      <section class="config-pane ${activeConfigTab === 'current' ? 'active' : ''}" data-config-pane="current">
        <div class="config-pane-head">
          <div>
            <h3>Current Device Configuration</h3>
            <p class="config-pane-subtitle">View and manage latest running configuration.</p>
          </div>
          <div class="config-actions">
            <button type="button" class="action-btn" data-config-action="view">View Config</button>
            <button type="button" class="action-btn" data-config-action="download">Download</button>
            <button type="button" class="action-btn" data-config-action="copy">Copy</button>
            <button type="button" class="action-btn" data-config-action="refresh">Refresh</button>
          </div>
        </div>
        <div class="config-action-row">
          <input type="text" class="form-input config-inline-search" data-config-interface-search="true" value="${esc(configInterfaceSearchTerm)}" placeholder="Search interface (e.g. ge-0/0/0, gi0/1)..." aria-label="Search interface config" />
        </div>
        <div class="config-layout-2">
          <div class="config-card code-view config-code-panel">
            <div class="config-subtabs">
              <button type="button" class="action-btn ${leftMode === 'hierarchical' ? 'primary' : ''}" data-config-current-view="hierarchical">Hierarchical</button>
              <button type="button" class="action-btn ${leftMode === 'raw' ? 'primary' : ''}" data-config-current-view="raw">Raw</button>
            </div>
            <h4>Selected Configuration (${leftMode === 'raw' ? 'Raw' : 'Hierarchical'})</h4>
            <div class="config-current-view" data-config-current-pane="hierarchical">
              <pre>${esc(leftConfigText || `No ${leftMode} config loaded. Use View Config.`)}</pre>
            </div>
          </div>
          <div class="config-card code-view config-code-panel">
            <div class="config-subtabs">
              <button type="button" class="action-btn ${rightMode === 'hierarchical' ? 'primary' : ''}" data-config-filter-view="hierarchical">Hierarchical</button>
              <button type="button" class="action-btn ${rightMode === 'raw' ? 'primary' : ''}" data-config-filter-view="raw">Raw</button>
            </div>
            <h4>Interface Filtered Output (${rightMode === 'raw' ? 'Raw' : 'Hierarchical'})</h4>
            <div class="config-current-view" data-config-current-pane="raw">
              <pre>${esc(rightConfigText || 'No filtered output available.')}</pre>
            </div>
          </div>
        </div>

        <div class="config-lower-grid">
          <div class="config-card terminal-card">
            <h4>SSH Terminal</h4>
            <p>Connect to device using SSH protocol</p>
            <div class="terminal-form-row">
              <div>
                <label>Hostname / IP</label>
                <input class="form-input" value="${esc(device.mgmtIp || '')}" />
                <label>Username</label>
                <input class="form-input" value="admin" />
                <label>Password</label>
                <input class="form-input" type="password" value="password" />
                <button type="button" class="action-btn primary terminal-connect-btn">Connect</button>
              </div>
              <pre class="terminal-preview">${esc(terminalPreview || '$ session not initialized')}</pre>
            </div>
          </div>
        </div>
      </section>

      <section class="config-pane ${activeConfigTab === 'backup' ? 'active' : ''}" data-config-pane="backup">
        <h3>Backup Configuration</h3>
        <div class="config-card backup-card">
          <h4>Backup Configuration</h4>
          <p>${hasSelectedDevice ? `Select date and time to view backup configuration for ${esc(device.hostname || device.mgmtIp)}.` : 'Select a device to view backup snapshots.'}</p>
          <div class="backup-toolbar-row">
            <input class="form-input" value="18 Oct 2024" aria-label="backup date" />
            <input class="form-input" value="10:00" aria-label="backup time" />
            <button type="button" class="action-btn primary">Search</button>
          </div>
          <div class="backup-table-wrap">
            <table class="backup-table">
              <thead><tr><th>#</th><th>Date & Time</th><th>Config Type</th><th>Size</th><th>Actions</th></tr></thead>
              <tbody>
                ${backupRows.map((row, idx) => `<tr><td>${idx + 1}</td><td>${esc(row.dt)}</td><td>${esc(row.type)}</td><td>${esc(row.size)}</td><td>View Download Restore</td></tr>`).join('')}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <section class="config-pane ${activeConfigTab === 'terminal' ? 'active' : ''}" data-config-pane="terminal">
        <h3>SSH Terminal</h3>
        <div class="config-card">${hasSelectedDevice ? `Terminal context prepared for ${esc(device.hostname || device.mgmtIp)}.` : 'Select a device before launching terminal.'}</div>
      </section>

      <section class="config-pane ${activeConfigTab === 'compare' ? 'active' : ''}" data-config-pane="compare">
        <h3>Config Compare</h3>
        <div class="config-card">${hasSelectedDevice ? 'Compare running/startup/current backups once backend diff API is enabled.' : 'Select a device to compare configurations.'}</div>
      </section>

      <section class="config-pane ${activeConfigTab === 'history' ? 'active' : ''}" data-config-pane="history">
        <h3>Config History</h3>
        <div class="config-card">Track changes by timestamp, user, change type and rollback action.</div>
      </section>

      <section class="config-pane ${activeConfigTab === 'templates' ? 'active' : ''}" data-config-pane="templates">
        <h3>Template Management</h3>
        <div class="config-card">Create/Edit/Delete/Apply reusable templates for SNMP, NTP, OSPF, BGP and interfaces.</div>
      </section>

      <section class="config-pane ${activeConfigTab === 'schedule' ? 'active' : ''}" data-config-pane="schedule">
        <h3>Scheduled Backups</h3>
        <div class="config-card">Daily/Weekly/Monthly backup scheduling with manual backup trigger.</div>
      </section>

      <section class="config-pane ${activeConfigTab === 'deploy' ? 'active' : ''}" data-config-pane="deploy">
        <h3>Config Deployment</h3>
        <div class="config-card">Validate, Preview, Deploy and Rollback workflow for safe change delivery.</div>
      </section>

      <section class="config-pane ${activeConfigTab === 'compliance' ? 'active' : ''}" data-config-pane="compliance">
        <h3>Compliance Dashboard</h3>
        <div class="config-card">AAA, NTP, SNMP, Syslog, Banner and SSH checks with compliance score.</div>
      </section>

      <section class="config-pane ${activeConfigTab === 'facts' ? 'active' : ''}" data-config-pane="facts">
        <h3>Device Facts</h3>
        <div class="config-facts-grid">
          <div class="config-card"><label>Hostname</label><strong>${esc(device.hostname || '-')}</strong></div>
          <div class="config-card"><label>Vendor</label><strong>${esc(device.vendor || '-')}</strong></div>
          <div class="config-card"><label>Model</label><strong>${esc(device.model || '-')}</strong></div>
          <div class="config-card"><label>OS</label><strong>${esc(device.osVersion || '-')}</strong></div>
          <div class="config-card"><label>CPU</label><strong>${latestHealthMetrics.cpu === null ? '--' : `${latestHealthMetrics.cpu}%`}</strong></div>
          <div class="config-card"><label>Memory</label><strong>${latestHealthMetrics.memory === null ? '--' : `${latestHealthMetrics.memory}%`}</strong></div>
          <div class="config-card"><label>Uptime</label><strong>${esc(latestHealthMetrics.uptime || '--')}</strong></div>
          <div class="config-card"><label>Status</label><strong>${status.label}</strong></div>
        </div>
      </section>
    `;
  };

  const activateConfigTab = (tabId) => {
    if (!configDeviceContent) {
      return;
    }
    activeConfigTab = tabId;
    configDeviceContent.querySelectorAll('.config-tab').forEach((tab) => {
      tab.classList.toggle('active', tab.getAttribute('data-config-tab') === tabId);
    });
    configDeviceContent.querySelectorAll('.config-pane').forEach((pane) => {
      pane.classList.toggle('active', pane.getAttribute('data-config-pane') === tabId);
    });
  };

  const renderInventory = () => {
    if (!inventoryTableBody) {
      return;
    }

    const visibleItems = inventorySeed.filter((item) => String(item.status || '') === 'Discovered');

    const filteredItems = visibleItems.filter((item) => {
      if (!inventorySearchTerm) {
        return true;
      }
      const blob = `${item.hostname || ''} ${item.mgmtIp || ''} ${item.vendor || ''} ${item.model || ''}`.toLowerCase();
      return blob.includes(inventorySearchTerm);
    });

    inventoryTableBody.innerHTML = filteredItems
      .map((item) => `
        <tr>
          <td><button type="button" class="host-link" data-host-ip="${item.mgmtIp}">${esc(item.hostname || item.mgmtIp || 'unknown')}</button></td>
          <td>${item.mgmtIp}</td>
          <td>${esc(item.vendor || '-')}</td>
          <td>${esc(item.model || '-')}</td>
          <td>${esc(item.osVersion || '-')}</td>
          <td><span class="status-pill status-${String(item.status || '').toLowerCase().replace(/\s+/g, '-')}">${esc(item.status || 'Unknown')}</span></td>
          <td><button type="button" class="row-delete-btn" data-delete-ip="${item.mgmtIp}">Delete</button></td>
        </tr>
      `)
      .join('');

    if (filteredItems.length === 0) {
      inventoryTableBody.innerHTML = `
        <tr>
          <td colspan="7">No matching devices found.</td>
        </tr>
      `;
    }

    if (inventoryCount) {
      inventoryCount.textContent = `${filteredItems.length} device${filteredItems.length === 1 ? '' : 's'}`;
    }
  };

  const subnetBase = (subnetCidr) => {
    const normalized = String(subnetCidr || '').split('/')[0];
    const parts = normalized.split('.');
    if (parts.length !== 4) {
      return null;
    }
    return `${parts[0]}.${parts[1]}.${parts[2]}`;
  };

  const syncSubnetOptions = () => {
    if (!subnetFilter) {
      return;
    }
    const current = subnetFilter.value;
    subnetFilter.innerHTML = '<option value="ALL">All Subnets</option>';
    configuredSubnets.forEach((subnet) => {
      const option = document.createElement('option');
      option.value = subnet;
      option.textContent = subnet;
      subnetFilter.appendChild(option);
    });
    subnetFilter.value = configuredSubnets.includes(current) || current === 'ALL' ? current : 'ALL';
  };

  const syncHostOptions = () => {
    if (!hostFilter) {
      return;
    }

    const selectedSubnet = subnetFilter ? subnetFilter.value : 'ALL';
    const currentHost = hostFilter.value;
    hostFilter.innerHTML = '<option value="ALL">All IPs</option>';

    if (selectedSubnet === 'ALL') {
      const ips = Array.from(new Set(inventorySeed.map((item) => item.mgmtIp))).sort();
      ips.forEach((ip) => {
        const option = document.createElement('option');
        option.value = ip;
        option.textContent = ip;
        hostFilter.appendChild(option);
      });
    } else {
      const base = subnetBase(selectedSubnet);
      if (!base) {
        return;
      }
      for (let i = hostMin; i <= hostMax; i += 1) {
        const ip = `${base}.${i}`;
        const option = document.createElement('option');
        option.value = ip;
        option.textContent = `.${i} (${ip})`;
        hostFilter.appendChild(option);
      }
    }

    const hasCurrent = Array.from(hostFilter.options).some((opt) => opt.value === currentHost);
    hostFilter.value = hasCurrent ? currentHost : 'ALL';
  };

  const selectedScope = () => ({
    subnet: subnetFilter ? subnetFilter.value : 'ALL',
    host_ip: hostFilter ? hostFilter.value : 'ALL'
  });

  const loadInventory = async () => {
    const scope = selectedScope();
    const params = new URLSearchParams();
    if (scope.subnet && scope.subnet !== 'ALL') {
      params.set('subnet', scope.subnet);
    }
    if (scope.host_ip && scope.host_ip !== 'ALL') {
      params.set('host_ip', scope.host_ip);
    }
    const url = `${API_BASE}/api/inventory${params.toString() ? `?${params.toString()}` : ''}`;
    try {
      const response = await fetch(url);
      if (!response.ok) {
        throw new Error(`Inventory fetch failed (${response.status})`);
      }
      const payload = await response.json();
      setBackendStatus('connected');
      inventorySeed = mapInventoryItems(payload.items || []);
      renderInventory();
      renderDashboard();
      syncHostOptions();
      syncDetailDeviceOptions();
    } catch (error) {
      inventorySeed = [];
      renderInventory();
      renderDashboard();
      syncDetailDeviceOptions();
      setBackendStatus('disconnected', 'unreachable');
      setFeedback('Cannot connect to backend API on port 8788.', 'error');
    }
  };

  const runRefreshData = async () => {
    if (operationInProgress) {
      return;
    }

    operationInProgress = true;
    try {
      const scope = selectedScope();
      const response = await fetch(`${API_BASE}/api/inventory/netconf-yang-safe-scan`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          subnet: scope.subnet,
          host_ip: 'ALL',
          timeout_seconds: 8.0,
          max_concurrency: 12,
          max_retries: 1
        })
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail || `Refresh failed (${response.status})`);
      }

      setBackendStatus('connected');
      inventorySeed = mapInventoryItems(payload.items || []);
      renderInventory();
      renderDashboard();

      const discovered = inventorySeed.filter((item) => String(item.status || '') === 'Discovered').length;
      const failed = inventorySeed.filter((item) => String(item.status || '') === 'Fetch Failed').length;
      setLiveRefreshMeta(`Live: ${discovered} ok / ${failed} failed`, `Last refresh: ${new Date().toLocaleTimeString()}`);
      setFeedback('Data refreshed successfully.', 'success');
    } catch (error) {
      setBackendStatus('disconnected', 'API error');
      setFeedback(String(error.message || 'Failed to refresh data.'), 'error');
    } finally {
      operationInProgress = false;
    }
  };

  const deleteByIp = async (ip) => {
    const ok = window.confirm(`Delete IP ${ip} from inventory?`);
    if (!ok) {
      return;
    }

    try {
      const response = await fetch(`${API_BASE}/api/inventory/ip/${encodeURIComponent(ip)}`, {
        method: 'DELETE'
      });
      if (!response.ok) {
        throw new Error(`Delete failed (${response.status})`);
      }
      setBackendStatus('connected');
      await loadInventory();
      setFeedback(`Deleted ${ip} from inventory.`, 'success');
    } catch (error) {
      setBackendStatus('disconnected', 'API error');
      setFeedback('Failed to delete IP from backend API.', 'error');
    }
  };

  const deleteSelectedSubnet = async () => {
    if (!subnetFilter) {
      return;
    }
    const selectedSubnet = subnetFilter.value;
    if (selectedSubnet === 'ALL') {
      setFeedback('Select a specific subnet before bulk delete.', 'error');
      return;
    }

    const ok = window.confirm(`Delete all visible device IPs under ${selectedSubnet}?`);
    if (!ok) {
      return;
    }

    try {
      const encoded = encodeURIComponent(selectedSubnet.replace('/', '~'));
      const response = await fetch(`${API_BASE}/api/inventory/subnet/${encoded}`, {
        method: 'DELETE'
      });
      if (!response.ok) {
        throw new Error(`Delete subnet failed (${response.status})`);
      }
      setBackendStatus('connected');
      await loadInventory();
      setFeedback(`Deleted IPs under ${selectedSubnet}.`, 'success');
    } catch (error) {
      setBackendStatus('disconnected', 'API error');
      setFeedback('Failed to delete subnet IPs from backend API.', 'error');
    }
  };

  const showView = (viewId) => {
    panels.forEach((panel) => {
      panel.classList.toggle('is-active', panel.dataset.viewPanel === viewId);
    });
    if (subtitle && subtitles[viewId]) {
      subtitle.textContent = subtitles[viewId];
    }
    if (viewId === 'inventory') {
      stopInterfacePolling();
      loadInventory();
    }
    if (viewId === 'detail') {
      renderDetailView();
      startInterfacePolling();
    }
    if (viewId === 'config') {
      if (selectedDevice && selectedDevice.mgmtIp) {
        fetchCurrentConfigForMode(activeConfigCurrentView).then(() => {
          renderDeviceConfigView();
        });
      } else {
        renderDeviceConfigView();
      }
      startInterfacePolling();
    }
    if (viewId === 'dashboard') {
      stopInterfacePolling();
      renderDashboard();
    }
  };

  navItems.forEach((item) => {
    item.addEventListener('click', () => {
      navItems.forEach((button) => button.classList.remove('active'));
      item.classList.add('active');
      const viewId = item.dataset.view;
      if (viewId) {
        showView(viewId);
      }
    });
  });

  if (subnetFilter) {
    subnetFilter.addEventListener('change', async () => {
      syncHostOptions();
      await loadInventory();
    });
  }

  if (hostFilter) {
    hostFilter.addEventListener('change', async () => {
      await loadInventory();
    });
  }

  if (inventorySearch) {
    inventorySearch.addEventListener('input', () => {
      inventorySearchTerm = String(inventorySearch.value || '').trim().toLowerCase();
      renderInventory();
    });
  }

  if (detailInterfaceSearch) {
    detailInterfaceSearch.addEventListener('input', () => {
      detailInterfaceSearchTerm = String(detailInterfaceSearch.value || '').trim().toLowerCase();
      interfacePage = 1;
      renderDetailView();
    });
  }

  if (globalDeviceSearch) {
    globalDeviceSearch.addEventListener('input', () => {
      const query = String(globalDeviceSearch.value || '').trim().toLowerCase();
      inventorySearchTerm = query;
      renderInventory();
      const found = inventorySeed.find((item) => `${item.hostname || ''} ${item.mgmtIp || ''}`.toLowerCase().includes(query));
      if (found && query.length >= 2) {
        setSelectedDevice(found, `Polling interfaces for ${found.hostname}...`);
        navItems.forEach((button) => button.classList.remove('active'));
        const detailButton = document.querySelector('.nav-item[data-view="detail"]');
        if (detailButton) {
          detailButton.classList.add('active');
        }
        showView('detail');
      }
    });
  }

  if (configDeviceContent) {
    configDeviceContent.addEventListener('click', (event) => {
      const target = event.target;
      if (!(target instanceof HTMLElement)) {
        return;
      }

      const currentView = target.getAttribute('data-config-current-view');
      if (currentView) {
        activeConfigCurrentView = currentView;
        fetchCurrentConfigForMode(currentView).then(() => {
          renderDeviceConfigView();
        });
        return;
      }

      const filterView = target.getAttribute('data-config-filter-view');
      if (filterView) {
        activeConfigFilterView = filterView;
        fetchCurrentConfigForMode(filterView).then(() => {
          renderDeviceConfigView();
        });
        return;
      }

      const action = target.getAttribute('data-config-action');
      if (action) {
        if (!selectedDevice) {
          setConfigFeedback('Device not found. Select a valid device first.', 'error');
          return;
        }
        if (action === 'view') {
          fetchCurrentConfigForMode(activeConfigCurrentView, true).then(() => {
            renderDeviceConfigView();
            setConfigFeedback(`Showing ${activeConfigCurrentView} configuration for ${selectedDevice.hostname || selectedDevice.mgmtIp}.`, 'success');
          });
          return;
        }
        if (action === 'refresh') {
          setSelectedDevice(selectedDevice, `Refreshing config context for ${selectedDevice.hostname || selectedDevice.mgmtIp}...`);
          setConfigFeedback('Configuration data refreshed from latest telemetry.', 'success');
          return;
        }
        const fallbackText = buildRawConfigText(selectedDevice);
        const sourceText = (activeConfigCurrentView === 'raw' ? configModePayload.raw.content : configModePayload.hierarchical.content) || fallbackText;
        if (action === 'copy') {
          if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(sourceText)
              .then(() => setConfigFeedback('Raw configuration copied to clipboard.', 'success'))
              .catch(() => setConfigFeedback('Copy failed. Clipboard permission not available.', 'error'));
          } else {
            setConfigFeedback('Copy not supported in this browser context.', 'error');
          }
          return;
        }
        if (action === 'download') {
          const blob = new Blob([sourceText], { type: 'text/plain;charset=utf-8' });
          const url = URL.createObjectURL(blob);
          const anchor = document.createElement('a');
          const nameBase = (selectedDevice.hostname || selectedDevice.mgmtIp || 'device').replace(/\s+/g, '_');
          anchor.href = url;
          anchor.download = `${nameBase}_running_config.txt`;
          document.body.appendChild(anchor);
          anchor.click();
          anchor.remove();
          URL.revokeObjectURL(url);
          setConfigFeedback('Configuration download started.', 'success');
          return;
        }
      }

      const tabId = target.getAttribute('data-config-tab');
      if (tabId) {
        activateConfigTab(tabId);
      }
    });
  }

  if (configDeviceSearch) {
    configDeviceSearch.addEventListener('input', () => {
      selectedDevice = null;
      resetConfigModePayload();
      activeConfigCurrentView = 'hierarchical';
      renderDeviceConfigView();
      setConfigFeedback('');
    });

    configDeviceSearch.addEventListener('keydown', (event) => {
      if (event.key !== 'Enter') {
        return;
      }
      event.preventDefault();
      const query = String(configDeviceSearch.value || '').trim().toLowerCase();
      if (!query) {
        setConfigFeedback('Type hostname or management IP to search.', 'error');
        return;
      }
      const found = findBestDeviceMatch(query, { requireDiscovered: true });
      if (found) {
        activeConfigTab = 'current';
        activeConfigCurrentView = 'hierarchical';
        activeConfigFilterView = 'hierarchical';
        configInterfaceSearchTerm = '';
        setSelectedDevice(found, `Fetching config context for ${found.hostname || found.mgmtIp}...`);
        fetchCurrentConfigForMode('hierarchical', true).then(() => {
          renderDeviceConfigView();
          setConfigFeedback(`Device selected: ${found.hostname || found.mgmtIp}`, 'success');
        });
        return;
      }
      selectedDevice = null;
      resetConfigModePayload();
      renderDeviceConfigView();
      setConfigFeedback(`Device not found in discovered inventory for "${query}".`, 'error');
    });
  }

  if (configDeviceSync) {
    configDeviceSync.addEventListener('click', () => {
      const query = String(configDeviceSearch?.value || '').trim();
      if (query) {
        const found = findBestDeviceMatch(query, { requireDiscovered: true });
        if (!found) {
          selectedDevice = null;
          resetConfigModePayload();
          renderDeviceConfigView();
          setConfigFeedback(`Device not found in discovered inventory for "${query}".`, 'error');
          return;
        }

        activeConfigTab = 'current';
        activeConfigCurrentView = 'hierarchical';
        activeConfigFilterView = 'hierarchical';
        configInterfaceSearchTerm = '';
        setSelectedDevice(found, `Fetching config context for ${found.hostname || found.mgmtIp}...`);
        fetchCurrentConfigForMode(activeConfigCurrentView, true).then(() => {
          setConfigFeedback(`Using selected device: ${found.hostname || found.mgmtIp}`, 'success');
          renderDeviceConfigView();
        });
        return;
      }

      if (!selectedDevice) {
        setConfigFeedback('Device not found. Select a valid device first.', 'error');
        renderDeviceConfigView();
        return;
      }
      fetchCurrentConfigForMode(activeConfigCurrentView, true).then(() => {
        setConfigFeedback(`Using selected device: ${selectedDevice.hostname || selectedDevice.mgmtIp}`, 'success');
        renderDeviceConfigView();
      });
    });
  }

  if (configDeviceContent) {
    configDeviceContent.addEventListener('input', (event) => {
      const target = event.target;
      if (!(target instanceof HTMLElement)) {
        return;
      }
      if (target.getAttribute('data-config-interface-search') === 'true') {
        configInterfaceSearchTerm = String(target.value || '').trim();
        renderDeviceConfigView();
      }
    });
  }

  if (globalRefreshBtn) {
    globalRefreshBtn.addEventListener('click', async () => {
      await runRefreshData();
      if (headerLastUpdated) {
        headerLastUpdated.textContent = `Last Updated: ${new Date().toLocaleString()}`;
      }
    });
  }

  if (detailDeviceSearch) {
    detailDeviceSearch.addEventListener('input', () => {
      autoSelectDeviceFromDetailSearch();
    });
    detailDeviceSearch.addEventListener('keydown', (event) => {
      if (event.key === 'Enter') {
        event.preventDefault();
        selectDeviceFromDetailSearch();
      }
    });
    detailDeviceSearch.addEventListener('change', () => {
      selectDeviceFromDetailSearch();
    });
  }

  if (themeSwitcher) {
    themeSwitcher.addEventListener('change', () => {
      applyTheme(themeSwitcher.value);
    });
  }

  if (inventoryTableBody) {
    inventoryTableBody.addEventListener('click', async (event) => {
      const target = event.target;
      if (!(target instanceof HTMLElement)) {
        return;
      }
      const ip = target.getAttribute('data-delete-ip');
      if (ip) {
        await deleteByIp(ip);
        return;
      }

      const hostIp = target.getAttribute('data-host-ip');
      if (!hostIp) {
        return;
      }

      selectedDevice = inventorySeed.find((item) => item.mgmtIp === hostIp) || null;
      if (selectedDevice) {
        setSelectedDevice(selectedDevice, `Fetching live telemetry for ${selectedDevice.hostname || selectedDevice.mgmtIp}...`);
      }
      if (selectedDevice && detailDeviceSearch) {
        detailDeviceSearch.value = selectedDevice.hostname || selectedDevice.mgmtIp || '';
        updateDetailDeviceMatchBadge();
      }
      showView('detail');
      navItems.forEach((button) => button.classList.remove('active'));
      const detailButton = document.querySelector('.nav-item[data-view="detail"]');
      if (detailButton) {
        detailButton.classList.add('active');
      }
    });
  }

  if (refreshDataBtn) {
    refreshDataBtn.textContent = 'Refresh Data';
    refreshDataBtn.addEventListener('click', async () => {
      await runRefreshData();
    });
  }

  if (deleteSubnetBtn) {
    deleteSubnetBtn.addEventListener('click', async () => {
      await deleteSelectedSubnet();
    });
  }

  if (addIpToggle && addForm) {
    addIpToggle.addEventListener('click', () => {
      addForm.classList.toggle('open');
    });
  }

  if (addFormCancel && addForm) {
    addFormCancel.addEventListener('click', () => {
      addForm.classList.remove('open');
      setFeedback('');
    });
  }

  if (addForm) {
    addForm.addEventListener('submit', async (event) => {
      event.preventDefault();

      const subnet = String(addSubnet.value || '').trim();
      const hostStart = Number(addHostStart.value);
      const hostEnd = Number(addHostEnd.value);

      if (subnet !== subnetUnderTest) {
        setFeedback(`Only subnet ${subnetUnderTest} is allowed in this test scope.`, 'error');
        return;
      }

      const base = subnetBase(subnet);
      if (!base || !Number.isInteger(hostStart) || !Number.isInteger(hostEnd)) {
        setFeedback('Enter valid integer values for Host Start and Host End.', 'error');
        return;
      }

      if (hostStart < hostMin || hostStart > hostMax || hostEnd < hostMin || hostEnd > hostMax) {
        setFeedback(`Host must be in range ${hostMin}-${hostMax} for ${subnetUnderTest}.`, 'error');
        return;
      }

      if (hostStart > hostEnd) {
        setFeedback('Host Start must be less than or equal to Host End.', 'error');
        return;
      }

      try {
        const response = await fetch(`${API_BASE}/api/inventory/range-add`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            subnet,
            host_start: hostStart,
            host_end: hostEnd
          })
        });

        const payload = await response.json();
        if (!response.ok) {
          throw new Error(payload.detail || 'Range add failed');
        }

        setBackendStatus('connected');
        syncSubnetOptions();
        subnetFilter.value = subnet;
        syncHostOptions();
        hostFilter.value = 'ALL';
        await loadInventory();
        addForm.reset();
        addSubnet.value = subnetUnderTest;
        addForm.classList.remove('open');
        setFeedback(payload.message || 'Range added.', 'success');
      } catch (error) {
        setBackendStatus('disconnected', 'API error');
        setFeedback(String(error.message || 'Failed to add range via backend API.'), 'error');
      }
    });
  }

  showView('dashboard');
  try {
    applyTheme(localStorage.getItem('nms-theme') || 'light');
  } catch (err) {
    applyTheme('light');
  }
  syncSubnetOptions();
  syncHostOptions();
  setBackendStatus('unknown');
  setLiveRefreshMeta();
  if (headerLastUpdated) {
    headerLastUpdated.textContent = `Last Updated: ${new Date().toLocaleString()}`;
  }
  loadInventory();
  renderDashboard();
  updateDetailDeviceMatchBadge();
  renderDetailView();
  renderDeviceConfigView();
})();
