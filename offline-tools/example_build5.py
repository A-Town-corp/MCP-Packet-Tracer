"""Build 5 DISTINCT company network topologies as PT deploy plans.

Each network: 5 routers (2911, 3 GigE ports), >=3 switches, 10 PCs, OSPF
(single `network 10.i.0.0 0.0.255.255 area 0` per router) + DHCP per LAN.
Unique /16 per network (10.i.0.0/16). Coordinates are laid out per-topology with
generous margins so nothing hugs the canvas edge.
"""
import json
import os
import tempfile

# ---- topology specs: routers with RELATIVE positions, r-r links, LAN sizes ----
# lan_pcs maps a router -> number of PCs on its LAN (0 = no LAN/switch on it)
# grid placement (2 columns) keeps the whole thing compact + well-margined.
GRID = {1:(0,0), 2:(1,0), 3:(0,1), 4:(1,1), 5:(0,2)}
COL_W, ROW_H, MX, MY = 1120, 560, 160, 130

NETS = {
 1: {"label":"Hub-and-Spoke", "order":["R1","R2","R3","R4","R5"],
     "rlinks":[("R1","R2"),("R1","R3"),("R1","R4"),("R2","R5")],
     "lan_pcs":{"R2":3,"R3":3,"R4":2,"R5":2}},   # hub R1 has no LAN (3 link ports)
 2: {"label":"Redundant Ring", "order":["R1","R2","R3","R4","R5"],
     "rlinks":[("R1","R2"),("R2","R3"),("R3","R4"),("R4","R5"),("R5","R1")],
     "lan_pcs":{"R1":2,"R2":2,"R3":2,"R4":2,"R5":2}},
 3: {"label":"Dual-Core Mesh", "order":["R3","R1","R5","R2","R4"],
     "rlinks":[("R1","R2"),("R1","R3"),("R2","R4"),("R1","R5"),("R2","R5")],
     "lan_pcs":{"R3":4,"R4":3,"R5":3}},          # cores R1,R2 no LAN
 4: {"label":"Branch Chain", "order":["R1","R2","R3","R4","R5"],
     "rlinks":[("R1","R2"),("R2","R3"),("R3","R4"),("R4","R5")],
     "lan_pcs":{"R1":2,"R2":2,"R3":2,"R4":2,"R5":2}},
 5: {"label":"Tree", "order":["R4","R2","R1","R3","R5"],
     "rlinks":[("R1","R2"),("R1","R3"),("R2","R4"),("R3","R5")],
     "lan_pcs":{"R1":2,"R2":2,"R3":2,"R4":2,"R5":2}},
}

summary=[]
for i,spec in NETS.items():
    gc,gr = GRID[i]; bx = MX + gc*COL_W; by = MY + gr*ROW_H
    B = lambda rx,ry: (bx+rx, by+ry)
    rlinks=spec["rlinks"]; lan_pcs=spec["lan_pcs"]
    # clean grid: routers in a row (order left->right), switch below LAN-router, PCs below switch
    routers={}
    for k,rn in enumerate(spec["order"]):
        routers[rn]=(70 + k*185, 30)
    devices=[]; links=[]; dhcp=[]; ospf=[]
    ports={r:["GigabitEthernet0/0","GigabitEthernet0/1","GigabitEthernet0/2"] for r in routers}
    iface={r:{} for r in routers}
    # router-router /30 links
    for n,(a,b) in enumerate(rlinks):
        sub=f"10.{i}.100.{n*4}"; ipa=f"10.{i}.100.{n*4+1}"; ipb=f"10.{i}.100.{n*4+2}"
        pa=ports[a].pop(0); pb=ports[b].pop(0)
        iface[a][pa]=ipa+"/30"; iface[b][pb]=ipb+"/30"
        links.append({"device_a":f"N{i}-{a}","port_a":pa,"device_b":f"N{i}-{b}","port_b":pb,"cable":"cross"})
    # LANs: switch + PCs per router that has a LAN
    lan_no=0
    for r,npc in lan_pcs.items():
        if npc<=0: continue
        lan_no+=1; net3=lan_no
        gw=f"10.{i}.{net3}.1"
        rp=ports[r].pop(0); iface[r][rp]=gw+"/24"
        rx,ry=routers[r]; sx,sy=rx,ry+135
        swn=f"N{i}-SW{lan_no}"
        devices.append({"name":swn,"model":"2960-24TT","category":"switch","x":B(sx,sy)[0],"y":B(sx,sy)[1]})
        links.append({"device_a":f"N{i}-{r}","port_a":rp,"device_b":swn,"port_b":"GigabitEthernet0/1","cable":"straight"})
        for p in range(npc):
            pcn=f"N{i}-{r}PC{p+1}"
            px=sx-60+ p*55; py=sy+125
            devices.append({"name":pcn,"model":"PC-PT","category":"pc","x":B(px,py)[0],"y":B(px,py)[1],
                            "interfaces":{"FastEthernet0":f"10.{i}.{net3}.{p+2}/24"},"gateway":gw})
            links.append({"device_a":swn,"port_a":f"FastEthernet0/{p+1}","device_b":pcn,"port_b":"FastEthernet0","cable":"straight"})
        dhcp.append({"router":f"N{i}-{r}","pool_name":f"LAN{lan_no}","network":f"10.{i}.{net3}.0","mask":"255.255.255.0",
                     "gateway":gw,"dns":"8.8.8.8","excluded_start":f"10.{i}.{net3}.1","excluded_end":f"10.{i}.{net3}.10"})
    # router devices + OSPF (single /16 statement)
    for rn,(rx,ry) in routers.items():
        devices.insert(0,{"name":f"N{i}-{rn}","model":"2911","category":"router","x":B(rx,ry)[0],"y":B(rx,ry)[1],
                          "interfaces":iface[rn]})
        ospf.append({"router":f"N{i}-{rn}","process_id":1,"router_id":f"{i}.{i}.{i}.{list(routers).index(rn)+1}",
                     "networks":[{"network":f"10.{i}.0.0","wildcard":"0.0.255.255","area":0}]})
    plan={"name":f"U{i}","devices":devices,"links":links,"dhcp_pools":dhcp,"ospf_configs":ospf}
    out = os.path.join(tempfile.gettempdir(), f"u{i}.json")  # portable temp dir (no hardcoded /tmp)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(plan, fh, separators=(",",":"))
    npc=sum(lan_pcs.values()); nsw=len([1 for v in lan_pcs.values() if v>0])
    summary.append((i,spec["label"],nsw,npc,len(links)))
    print(f"N{i} {spec['label']}: routers=5 switches={nsw} pcs={npc} links={len(links)} -> {out}")
print("\nDONE")
