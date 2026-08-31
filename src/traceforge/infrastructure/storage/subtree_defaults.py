"""Default org subtree tree for a hardware-oriented workspace."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SubtreeSeed:
    id: str
    code: str
    name: str
    level: int
    parent_id: str | None
    path: str
    sort_order: int = 0
    description: str | None = None


# Stable ids; codes used by Topic mapping and agent create arguments.
DEFAULT_SUBTREE_SEEDS: tuple[SubtreeSeed, ...] = (
    SubtreeSeed("st_software", "software", "软件", 1, None, "/st_software/", 10, "软件研发域"),
    SubtreeSeed(
        "st_software_embedded",
        "software.embedded",
        "嵌入式固件",
        2,
        "st_software",
        "/st_software/st_software_embedded/",
        10,
    ),
    SubtreeSeed(
        "st_software_embedded_boot",
        "software.embedded.bootloader",
        "Bootloader",
        3,
        "st_software_embedded",
        "/st_software/st_software_embedded/st_software_embedded_boot/",
        10,
    ),
    SubtreeSeed(
        "st_software_embedded_bsp",
        "software.embedded.bsp",
        "驱动与BSP",
        3,
        "st_software_embedded",
        "/st_software/st_software_embedded/st_software_embedded_bsp/",
        20,
    ),
    SubtreeSeed(
        "st_software_cloud",
        "software.cloud",
        "云边协同",
        2,
        "st_software",
        "/st_software/st_software_cloud/",
        20,
    ),
    SubtreeSeed(
        "st_software_cloud_agent",
        "software.cloud.agent",
        "TraceForge Agent",
        3,
        "st_software_cloud",
        "/st_software/st_software_cloud/st_software_cloud_agent/",
        10,
        "Workspace Agent / Todo / Memory 工具链",
    ),
    SubtreeSeed(
        "st_software_cloud_zulip",
        "software.cloud.zulip",
        "Zulip 集成",
        3,
        "st_software_cloud",
        "/st_software/st_software_cloud/st_software_cloud_zulip/",
        20,
    ),
    SubtreeSeed("st_hardware", "hardware", "硬件", 1, None, "/st_hardware/", 20, "硬件研发域"),
    SubtreeSeed(
        "st_hardware_mainboard",
        "hardware.mainboard",
        "主控板",
        2,
        "st_hardware",
        "/st_hardware/st_hardware_mainboard/",
        10,
    ),
    SubtreeSeed(
        "st_hardware_mainboard_sch",
        "hardware.mainboard.schematic",
        "原理图",
        3,
        "st_hardware_mainboard",
        "/st_hardware/st_hardware_mainboard/st_hardware_mainboard_sch/",
        10,
    ),
    SubtreeSeed(
        "st_hardware_mainboard_pcb",
        "hardware.mainboard.pcb",
        "PCB与打样",
        3,
        "st_hardware_mainboard",
        "/st_hardware/st_hardware_mainboard/st_hardware_mainboard_pcb/",
        20,
    ),
    SubtreeSeed(
        "st_hardware_rf",
        "hardware.rf",
        "电源与射频",
        2,
        "st_hardware",
        "/st_hardware/st_hardware_rf/",
        20,
    ),
    SubtreeSeed(
        "st_hardware_rf_pi",
        "hardware.rf.pi",
        "电源完整性",
        3,
        "st_hardware_rf",
        "/st_hardware/st_hardware_rf/st_hardware_rf_pi/",
        10,
    ),
    SubtreeSeed("st_other", "other", "其他", 1, None, "/st_other/", 30, "非产品线 / 闲聊与内部活动"),
    SubtreeSeed(
        "st_other_culture",
        "other.culture",
        "内部文化",
        2,
        "st_other",
        "/st_other/st_other_culture/",
        10,
    ),
    SubtreeSeed(
        "st_other_football",
        "other.football",
        "球迷社群",
        3,
        "st_other_culture",
        "/st_other/st_other_culture/st_other_football/",
        10,
        "football 等闲聊 Topic",
    ),
)
