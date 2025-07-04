import os

import numpy as np
import pandas as pd

import excel as ex


def valid_data(data):
    if pd.isna(data.values).any():
        return False, data
    try:
        return True, data.astype(float)
    except (ValueError, TypeError):
        return False, data


def sanity_check_structure(excel_filename, df):
    # check, if sections are on top of each other
    height_diff = (df["Top [m]"].values[1:] - df["Bottom [m]"].values[:-1]) == 0
    if not all(height_diff):
        missaligned_sections = [int(df.iloc[i, 0]) for i, value in enumerate(height_diff) if not value]
        ex.show_message_box(excel_filename, f"The Sections are overlapping or have space in between at Section(s): {missaligned_sections} ")
        return False
    else:
        return True


def check_convert_structure(excel_filename, df: pd.DataFrame, Table):
    success, df = valid_data(df)
    if not success:
        ex.show_message_box(excel_filename, f"The {Table} Table containes invalid data (nan or non numerical)")
        return success, df

    success = sanity_check_structure
    return success, df


def center_of_mass_hollow_frustum(d1, d2, z_bot, z_top, t):
    """
    Calculates the center of mass (z-coordinate) of a hollow conical frustum
    (truncated cone) with constant wall thickness, based on absolute z-positions.

    Supports scalar, list, or numpy array input (all inputs must be same shape).

    Parameters:
    d1     : float, list, or np.ndarray - Inner diameter at the bottom
    d2     : float, list, or np.ndarray - Inner diameter at the top
    z_bot  : float, list, or np.ndarray - z-position of the bottom surface
    z_top  : float, list, or np.ndarray - z-position of the top surface
    t      : float, list, or np.ndarray - Constant wall thickness

    Returns:
    z_cm   : float or np.ndarray - z-position of the center of mass
    """
    # Convert to numpy arrays
    d1 = np.asarray(d1, dtype=np.float64)
    d2 = np.asarray(d2, dtype=np.float64)
    z_bot = np.asarray(z_bot, dtype=np.float64)
    z_top = np.asarray(z_top, dtype=np.float64)
    t = np.asarray(t, dtype=np.float64)

    # Compute height and radii
    h = z_top - z_bot
    r1 = d1 / 2
    r2 = d2 / 2
    R1 = r1 + t
    R2 = r2 + t

    # Volume and center of mass for solid frustum
    def volume(r1, r2, h):
        return (np.pi * h / 3) * (r1 ** 2 + r1 * r2 + r2 ** 2)

    def com_z_rel(r1, r2, h):
        num = r1 ** 2 + 2 * r1 * r2 + 3 * r2 ** 2
        den = r1 ** 2 + r1 * r2 + r2 ** 2
        return h * num / (4 * den)

    # Compute relative center of mass (from bottom), then convert to absolute z
    V_outer = volume(R1, R2, h)
    V_inner = volume(r1, r2, h)
    z_outer_rel = com_z_rel(R1, R2, h)
    z_inner_rel = com_z_rel(r1, r2, h)

    z_cm_rel = (z_outer_rel * V_outer - z_inner_rel * V_inner) / (V_outer - V_inner)
    z_cm_abs = z_bot + z_cm_rel

    return z_cm_abs


def calc_weight(rho, t, z_top, z_bot, d_top, d_bot):
    rho = np.asarray(rho)
    t = np.asarray(t)
    z_top = np.asarray(z_top)
    z_bot = np.asarray(z_bot)
    d_top = np.asarray(d_top)
    d_bot = np.asarray(d_bot)

    h = np.abs(z_top - z_bot)
    d1 = d_top
    d2 = d_bot

    volume = (1 / 3) * np.pi * h / 4 * (
            d1 ** 2 + d1 * d2 + d2 ** 2
            - (d1 - 2 * t) ** 2
            - (d1 - 2 * t) * (d2 - 2 * t)
            - (d2 - 2 * t) ** 2
    )

    return rho * volume


def add_element(df, z_new):
    """
    Inserts an interpolated node into a structural DataFrame at a specified height.

    If the height already exists as a "Top [m]" or "Bottom [m]" value, the original DataFrame is returned.
    Otherwise, if the height lies within exactly one segment (i.e., between "Top [m]" and "Bottom [m]" of a single row),
    a new row is inserted by interpolating the diameter at that height. The original segment is split accordingly.

    Parameters
    ----------
    df : pandas.DataFrame
        DataFrame containing structural node information with columns such as:
        - "Top [m]"
        - "Bottom [m]"
        - "D, top [m]"
        - "D, bottom [m]"
        - "t [mm]"
        - optionally: "Affiliation"
    height : float
        The height (in meters) at which to interpolate a new node.

    Returns
    -------
    pandas.DataFrame or None
        Updated DataFrame with the interpolated node inserted, or None if:
        - the height is outside the bounds of the structure, or
        - multiple segments contain the height (i.e., structure is not consecutive at that height).

    Notes
    -----
    - If interpolation is successful, the original segment is split, with the lower part ending at the new height,
      and a new row inserted on top with interpolated diameter.
    - The "Affiliation" of the new row is copied from the original row if the column exists.
    - No checks are made for column types or values; ensure input DataFrame is clean and valid.
    """
    df = df.reset_index(drop=True)
    if len(df.loc[(df["Top [m]"] == z_new) | (df["Bottom [m]"] == z_new)].index) > 0:
        return df

    id_inter = df.loc[(df["Top [m]"] > z_new) & (df["Bottom [m]"] < z_new)].index
    if len(id_inter) == 0:
        print("interpolation not possible, outside bounds")
        return df
    if len(id_inter) > 1:
        print("interpolation not possible, structure not consecutive")
        return df
    id_inter = id_inter[0]

    new_row = pd.DataFrame(columns=df.columns)

    if "Affiliation" in df.columns:
        new_row.loc[0, "Affiliation"] = df.loc[id_inter, "Affiliation"]

    new_row.loc[0, "t [mm]"] = df.loc[id_inter, "t [mm]"]

    # height
    new_row.loc[0, "Top [m]"] = z_new
    new_row.loc[0, "Bottom [m]"] = df.loc[id_inter, "Bottom [m]"]

    # diameter interpolation
    inter_x_rel = (z_new - df.loc[id_inter, "Bottom [m]"]) / (df.loc[id_inter, "Top [m]"] - df.loc[id_inter, "Bottom [m]"])
    d_inter = (df.loc[id_inter, "D, top [m]"] - df.loc[id_inter, "D, bottom [m]"]) * inter_x_rel + df.loc[id_inter, "D, bottom [m]"]
    new_row.loc[0, "D, top [m]"] = d_inter
    new_row.loc[0, "D, bottom [m]"] = df.loc[id_inter, "D, bottom [m]"]

    df = df.copy()
    # update original segment
    df.loc[id_inter, "Bottom [m]"] = z_new

    # insert new row
    df = pd.concat([df.iloc[:id_inter + 1], new_row, df.iloc[id_inter + 1:]]).reset_index(drop=True)

    return df


def assemble_structure(excel_caller, rho, RNA_config):
    def all_same_ignoring_none(*values):
        non_none = [v for v in values if v is not None]
        return len(non_none) <= 1 or all(v == non_none[0] for v in non_none)

    excel_filename = os.path.basename(excel_caller)
    # load structure Data
    MP_DATA = ex.read_excel_table(excel_filename, "BuildYourStructure", "MP_DATA")
    TP_DATA = ex.read_excel_table(excel_filename, "BuildYourStructure", "TP_DATA")
    TOWER_DATA = ex.read_excel_table(excel_filename, "BuildYourStructure", "TOWER_DATA")
    RNA_DATA = ex.read_excel_table(excel_filename, "BuildYourStructure", "RNA_DATA")

    MP_META = ex.read_excel_table(excel_filename, "BuildYourStructure", "MP_META")
    TP_META = ex.read_excel_table(excel_filename, "BuildYourStructure", "TP_META")
    TOWER_META = ex.read_excel_table(excel_filename, "BuildYourStructure", "TOWER_META")
    STRUCTURE_META = ex.read_excel_table(excel_filename, "StructureOverview", "STRUCTURE_META")
    STRUCTURE_META.loc[:, "Value"] = ""

    # Quality Checks/Warings of single datasets, if any fail fataly, abort
    sucess_MP, MP_DATA = check_convert_structure(excel_filename, MP_DATA, "MP")
    sucess_TP, TP_DATA = check_convert_structure(excel_filename, TP_DATA, "TP")
    sucess_TOWER, TOWER_DATA = check_convert_structure(excel_filename, TOWER_DATA, "TOWER")

    if not all([sucess_MP, sucess_TP, sucess_TOWER]):
        return

    # RNA
    if RNA_config == "":
        ex.show_message_box(excel_filename,
                            f"Caution, no RNA selected")
    else:
        if not RNA_config in RNA_DATA["Identifier"].values:
            ex.show_message_box(excel_filename,
                                f"Choosen RNA not in RNA dropdown menu. Aborting")
            return None
        else:
            RNA = RNA_DATA.loc[RNA_DATA["Identifier"] == RNA_config, :]
            ex.write_df_to_table(excel_filename, "StructureOverview", "RNA", RNA)

    # Height Reference handling
    WL_ref_MP = MP_META.loc[0, "Height Reference"]
    WL_ref_MT = TP_META.loc[0, "Height Reference"]
    WL_ref_TOWER = TOWER_META.loc[0, "Height Reference"]

    if not all_same_ignoring_none(WL_ref_MP, WL_ref_MT, WL_ref_TOWER):
        answer = ex.show_message_box(excel_filename,
                                     f"Warning, not all height references are the same (MP: {WL_ref_MP}, TP: {WL_ref_MT}, TOWER: {WL_ref_TOWER}). Assable anyway?",
                                     buttons="vbYesNo", icon="warning")
        if answer == "No":
            return
    else:
        STRUCTURE_META.loc[STRUCTURE_META["Parameter"] == "Height Reference", "Value"] = [v for v in [WL_ref_MP, WL_ref_MT, WL_ref_TOWER] if v is not None][0]
        ex.show_message_box(excel_filename,
                            f"Height references are the same or not defined. (MP: {WL_ref_MP}, TP: {WL_ref_MT}, TOWER: {WL_ref_TOWER}).")

    # waterdepth handling
    if MP_META.loc[0, "Water Depth [m]"] is not None:
        STRUCTURE_META.loc[STRUCTURE_META["Parameter"] == "Seabed level", "Value"] = - float(MP_META.loc[0, "Water Depth [m]"])
    MP_DATA.insert(0, "Affiliation", "MP")
    TP_DATA.insert(0, "Affiliation", "TP")
    TOWER_DATA.insert(0, "Affiliation", "TOWER")

    # Extract ranges
    range_MP = MP_DATA["Top [m]"].to_list() + list([MP_DATA["Bottom [m]"].values[-1]])
    range_TP = TP_DATA["Top [m]"].to_list() + list([TP_DATA["Bottom [m]"].values[-1]])

    # check MP TP connection
    if range_MP[0] < range_TP[-1]:
        ex.show_message_box(excel_filename,
                            f"The Top of the MP at {range_MP[0]} is lower than the Bottom of the TP at {range_TP[-1]}, so the TP is hovering midair at {range_TP[-1] - range_MP[0]}m over the MP. This cant work, aborting.")
        return
    WHOLE_STRUCTURE = MP_DATA

    # Add Weight column:
    # MP_DATA["Weight [t]"] = calc_weight(rho, MP_DATA["t [mm]"].values/1000, MP_DATA["Top [m]"].values, MP_DATA["Bottom [m]"].values, MP_DATA["D, top [m]"].values, MP_DATA["D, bottom [m]"].values)/1000
    # TP_DATA["Weight [t]"] = calc_weight(rho, TP_DATA["t [mm]"].values/1000, TP_DATA["Top [m]"].values, TP_DATA["Bottom [m]"].values, TP_DATA["D, top [m]"].values, TP_DATA["D, bottom [m]"].values)/1000
    # TOWER_DATA["Weight [t]"] = calc_weight(rho, TOWER_DATA["t [mm]"].values/1000, TOWER_DATA["Top [m]"].values, TOWER_DATA["Bottom [m]"].values, TOWER_DATA["D, top [m]"].values, TOWER_DATA["D, bottom [m]"].values)/1000

    # Assemble MP TP
    MP_top = range_MP[0]
    TP_bot = range_TP[-1]

    if MP_top > TP_bot:
        result = ex.show_message_box(excel_filename,
                                     f"The MP and the TP are overlapping by {-range_TP[-1] + range_MP[0]}m. Combine stiffness etc as grouted connection (yes) or add as skirt (no)?",
                                     buttons="vbYesNo", icon="vbYesNo", )

        if result == "Yes":

            ex.show_message_box(excel_filename,
                                f"under construction...")
        else:

            TP_DATA = add_element(TP_DATA, MP_top)
            SKIRT = TP_DATA.loc[TP_DATA["Top [m]"] <= MP_top]
            SKIRT.loc[:, "Affiliation"] = "SKIRT"
            SKIRT = SKIRT.drop("Section", axis=1)
            skirt_weights = calc_weight(rho, SKIRT["t [mm]"].values / 1000, SKIRT["Top [m]"].values, SKIRT["Bottom [m]"].values, SKIRT["D, top [m]"].values,
                                        SKIRT["D, bottom [m]"].values) / 1000
            skirt_heihgts = center_of_mass_hollow_frustum(SKIRT["D, bottom [m]"].values, SKIRT["D, top [m]"].values, SKIRT["Bottom [m]"], SKIRT["Top [m]"].values,
                                                          SKIRT["t [mm]"].values / 1000)
            skirt_weight = sum(skirt_weights)

            skirt_center_of_mass = sum([m * h for m, h in zip(list(skirt_weights), list(skirt_heihgts))]) / skirt_weight

            # cut TP
            TP_DATA = TP_DATA.loc[TP_DATA["Bottom [m]"] >= MP_top]
            WHOLE_STRUCTURE = pd.concat([TP_DATA, WHOLE_STRUCTURE], axis=0)

            SKIRT_POINTMASS = pd.DataFrame(columns=["Affiliation", "Elevation [m]", "Mass [t]", "comment"], index=[0])
            SKIRT_POINTMASS.loc[:, "Affiliation"] = "SKIRT"
            SKIRT_POINTMASS.loc[:, "Elevation [m]"] = skirt_center_of_mass
            SKIRT_POINTMASS.loc[:, "Mass [t]"] = skirt_weight
            SKIRT_POINTMASS.loc[:, "comment"] = "Skirt"

            ex.write_df_to_table(excel_filename, "StructureOverview", "SKIRT", SKIRT)
            ex.write_df_to_table(excel_filename, "StructureOverview", "SKIRT_POINTMASS", SKIRT_POINTMASS)

    else:
        ex.show_message_box(excel_filename, f"The MP and the TP are fitting together perfectly")

        WHOLE_STRUCTURE = pd.concat([TP_DATA, WHOLE_STRUCTURE], axis=0)

    # Add Tower
    tower_offset = WHOLE_STRUCTURE["Top [m]"].values[0] - TOWER_DATA["Bottom [m]"].values[-1]
    TOWER_DATA["Top [m]"] = TOWER_DATA["Top [m]"] + tower_offset
    TOWER_DATA["Bottom [m]"] = TOWER_DATA["Bottom [m]"] + tower_offset

    WHOLE_STRUCTURE = pd.concat([TOWER_DATA, WHOLE_STRUCTURE], axis=0)

    WHOLE_STRUCTURE.rename(columns={"Section": "local Section"}, inplace=True)
    WHOLE_STRUCTURE = WHOLE_STRUCTURE.reset_index(drop=True)
    WHOLE_STRUCTURE.insert(0, "Section", WHOLE_STRUCTURE.index.values + 1)
    ex.write_df_to_table(excel_filename, "StructureOverview", "WHOLE_STRUCTURE", WHOLE_STRUCTURE)

    # ADDED MASSES

    MP_MASSES = ex.read_excel_table(excel_filename, "BuildYourStructure", "MP_MASSES")
    TP_MASSES = ex.read_excel_table(excel_filename, "BuildYourStructure", "TP_MASSES")
    TOWER_MASSES = ex.read_excel_table(excel_filename, "BuildYourStructure", "TOWER_MASSES")

    TOWER_MASSES["Top [m]"] = TOWER_MASSES["Top [m]"] + tower_offset
    mask = pd.to_numeric(TOWER_MASSES["Bottom [m]"], errors='coerce').notna()
    TOWER_MASSES.loc[mask, "Bottom [m]"] += tower_offset

    MP_MASSES.insert(0, "Affiliation", "MP")
    TP_MASSES.insert(0, "Affiliation", "TP")
    TOWER_MASSES.insert(0, "Affiliation", "TOWER")

    ALL_MASSES = pd.concat([MP_MASSES, TP_MASSES, TOWER_MASSES], axis=0)
    ALL_MASSES.sort_values(inplace=True, ascending=False, axis=0, by=["Top [m]"])

    ex.write_df_to_table(excel_filename, "StructureOverview", "ALL_ADDED_MASSES", ALL_MASSES)
    ex.write_df_to_table(excel_filename, "StructureOverview", "STRUCTURE_META", STRUCTURE_META)

    return


def move_structure(excel_filename, displ, Structure):
    try:
        displ = float(displ)
    except ValueError:
        ex.show_message_box(excel_filename, f"Please enter a valid float value for the displacement.")
        return
    META_CURR = ex.read_excel_table(excel_filename, "BuildYourStructure", f"{Structure}_META", dtype=str)
    DATA_CURR = ex.read_excel_table(excel_filename, "BuildYourStructure", f"{Structure}_DATA", dtype=float)
    MASSES_CURR = ex.read_excel_table(excel_filename, "BuildYourStructure", f"{Structure}_MASSES")

    META_CURR.loc[:, "Height Reference"] = None
    DATA_CURR.loc[:, "Top [m]"] = DATA_CURR.loc[:, "Top [m]"] + displ
    DATA_CURR.loc[:, "Bottom [m]"] = DATA_CURR.loc[:, "Bottom [m]"] + displ
    MASSES_CURR.loc[:, "Top [m]"] = MASSES_CURR.loc[:, "Top [m]"] + displ
    MASSES_CURR.loc[:, "Bottom [m]"] = MASSES_CURR.loc[:, "Bottom [m]"] + displ

    ex.write_df_to_table(excel_filename, "BuildYourStructure", f"{Structure}_META", META_CURR)
    ex.write_df_to_table(excel_filename, "BuildYourStructure", f"{Structure}_DATA", DATA_CURR)
    ex.write_df_to_table(excel_filename, "BuildYourStructure", f"{Structure}_MASSES", MASSES_CURR)


def move_structure_MP(excel_caller, displ):
    excel_filename = os.path.basename(excel_caller)

    move_structure(excel_filename, displ, "MP")

    return


def move_structure_TP(excel_caller, displ):
    excel_filename = os.path.basename(excel_caller)

    move_structure(excel_filename, displ, "TP")

    return
