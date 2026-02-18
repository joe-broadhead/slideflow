def region_label(region: str = "unknown") -> str:
    return f"Region: {region}"


function_registry = {
    "region_label": region_label,
}
