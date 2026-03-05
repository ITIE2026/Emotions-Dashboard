"""
CalibrationStore – save / load calibration data as JSON.

Files are stored per-device serial in calibration_data/.
"""
import json
import os
from utils.config import CALIBRATION_DIR


def _path_for(serial: str) -> str:
    safe = serial.replace(":", "_").replace(" ", "_")
    return os.path.join(CALIBRATION_DIR, f"cal_{safe}.json")


def has_saved_calibration(serial: str) -> bool:
    return os.path.isfile(_path_for(serial))


def save_calibration(serial: str, data: dict):
    """Persist calibration data (nfb, prod_baselines, phy_baselines)."""
    with open(_path_for(serial), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def load_calibration(serial: str) -> dict | None:
    path = _path_for(serial)
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ── Helpers to serialise ctypes structs ───────────────────────────────
def nfb_to_dict(nfb) -> dict:
    """Convert IndividualNFBData to a plain dict."""
    return {
        "timestampMilli": int(nfb.timestampMilli),
        "failReason": int(nfb.failReason),
        "individualFrequency": float(nfb.individualFrequency),
        "individualPeakFrequency": float(nfb.individualPeakFrequency),
        "individualPeakFrequencyPower": float(nfb.individualPeakFrequencyPower),
        "individualPeakFrequencySuppression": float(nfb.individualPeakFrequencySuppression),
        "individualBandwidth": float(nfb.individualBandwidth),
        "individualNormalizedPower": float(nfb.individualNormalizedPower),
        "lowerFrequency": float(nfb.lowerFrequency),
        "upperFrequency": float(nfb.upperFrequency),
    }


def dict_to_nfb(d: dict):
    import sys
    from utils.config import CAPSULE_SDK_DIR
    if CAPSULE_SDK_DIR not in sys.path:
        sys.path.insert(0, CAPSULE_SDK_DIR)
    from Calibrator import IndividualNFBData
    return IndividualNFBData(
        timestamp_milli=d.get("timestampMilli", 1),
        individual_frequency=d.get("individualFrequency", 10.0),
        individual_peak_frequency=d.get("individualPeakFrequency", 10.0),
        individual_peak_frequency_power=d.get("individualPeakFrequencyPower", 10.0),
        individual_peak_frequency_suppression=d.get("individualPeakFrequencySuppression", 2.0),
        individual_bandwidth=d.get("individualBandwidth", 6.0),
        individual_normalized_power=d.get("individualNormalizedPower", 0.5),
        lower_frequency=d.get("lowerFrequency", 7.0),
        upper_frequency=d.get("upperFrequency", 13.0),
    )


def prod_baselines_to_dict(bl) -> dict:
    return {
        "timestampMilli": int(bl.timestampMilli),
        "gravity": float(bl.gravity),
        "productivity": float(bl.productivity),
        "fatigue": float(bl.fatigue),
        "reverseFatigue": float(bl.reverseFatigue),
        "relaxation": float(bl.relaxation),
        "concentration": float(bl.concentration),
    }


def dict_to_prod_baselines(d: dict):
    import sys
    from utils.config import CAPSULE_SDK_DIR
    if CAPSULE_SDK_DIR not in sys.path:
        sys.path.insert(0, CAPSULE_SDK_DIR)
    from Productivity import Productivity_Baselines
    bl = Productivity_Baselines(
        concentration=d.get("concentration", -1),
        fatigue=d.get("fatigue", -1),
        gravity=d.get("gravity", -1),
        productivity=d.get("productivity", -1),
        relax=d.get("relaxation", -1),
        reverse_fatigue=d.get("reverseFatigue", -1),
        timestamp=d.get("timestampMilli", -1),
    )
    return bl


def phy_baselines_to_dict(bl) -> dict:
    return {
        "timestampMilli": int(bl.timestampMilli),
        "alpha": float(bl.alpha),
        "beta": float(bl.beta),
        "alphaGravity": float(bl.alphaGravity),
        "betaGravity": float(bl.betaGravity),
        "concentration": float(bl.concentration),
    }


def dict_to_phy_baselines(d: dict):
    import sys
    from utils.config import CAPSULE_SDK_DIR
    if CAPSULE_SDK_DIR not in sys.path:
        sys.path.insert(0, CAPSULE_SDK_DIR)
    from PhysiologicalStates import PhysiologicalStates_Baselines
    return PhysiologicalStates_Baselines(
        timestamp_milli=d.get("timestampMilli", -1),
        alpha=d.get("alpha", -1.0),
        beta=d.get("beta", -1.0),
        alpha_gravity=d.get("alphaGravity", -1.0),
        beta_gravity=d.get("betaGravity", -1.0),
        concentration=d.get("concentration", -1.0),
    )
