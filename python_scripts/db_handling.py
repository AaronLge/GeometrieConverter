import xlwings
import pandas as pd
import sqlite3
import excel as ex


class ConciveError(Exception):
    """
    Custom exception for errors related to database operations
    in the context of structure data handling.
    """

    pass


log = ex.setup_logger()


def drop_db_table(db_path, Identifier):
    """
    Drop (delete) a table from an SQLite database completely.

    Args:
        db_path (str): Path to the SQLite database file.
        Identifier (str): Name of the table to drop.

    Raises:
        ConciveError: If database connection fails or drop operation fails.
    """
    try:
        conn = sqlite3.connect(db_path)
    except sqlite3.Error as e:
        raise ConciveError(f"Failed to connect to the database: {e}")

    cursor = conn.cursor()

    try:
        cursor.execute(f'DROP TABLE IF EXISTS "{Identifier}"')
        conn.commit()
    except sqlite3.Error as e:
        raise ConciveError(f"Failed to drop table '{Identifier}': {e}")
    finally:
        conn.close()


def load_db_table(db_path, Identifier, dtype=None):
    """
    Load a specific table from an SQLite database into a pandas DataFrame.

    Args:
        db_path (str): Path to the SQLite database file.
        Identifier (str): Name of the table to load.
        dtype (dict): Optional dictionary specifying column data types.

    Returns:
        pd.DataFrame: The table content as a pandas DataFrame.

    Raises:
        ConciveError: If database connection fails or table does not exist.
    """
    if not isinstance(Identifier, str):
        raise ConciveError(f"Identifier must be a string, got {type(Identifier)}.")

    try:
        conn = sqlite3.connect(db_path)
    except sqlite3.Error as e:
        raise ConciveError(f"Failed to connect to the database: {e}")

    try:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        table_names = [table[0] for table in cursor.fetchall()]
    except sqlite3.Error as e:
        conn.close()
        raise ConciveError(f"Failed to retrieve table names: {e}")

    if Identifier not in table_names:
        conn.close()
        raise ConciveError(f"Table '{Identifier}' does not exist in the database. Available tables: {table_names}")

    try:
        query = f'SELECT * FROM "{Identifier}"'
        df = pd.read_sql_query(query, conn)
    except Exception as e:
        conn.close()
        raise ConciveError(f"Failed to load table '{Identifier}': {e}")
    finally:
        conn.close()

    # Optional: Remove 'index' column if it exists
    if 'index' in df.columns:
        df = df.drop(columns=['index'])

    # Optional: Apply dtype conversion
    if dtype is not None:
        try:
            df = df.astype(dtype)
        except Exception as e:
            raise ConciveError(f"Failed to apply data types {dtype}: {e}")

    return df


def create_db_table(db_path, Identifier, df, if_exists='fail'):
    """
    Create a new table in an SQLite database from a pandas DataFrame.

    Args:
        db_path (str): Path to the SQLite database file.
        Identifier (str): Name of the table to create.
        df (pd.DataFrame): DataFrame containing the data to write.
        if_exists (str): What to do if the table already exists.
                         Options: 'fail', 'replace', 'append'.

    Raises:
        ConciveError: If database connection fails or table creation fails.
    """
    try:
        conn = sqlite3.connect(db_path)
    except sqlite3.Error as e:
        raise ConciveError(f"Failed to connect to the database: {e}")

    try:
        df.to_sql(Identifier, conn, if_exists=if_exists, index=False)
    except Exception as e:
        raise ConciveError(f"Failed to create or write to the table '{Identifier}': {e}")
    finally:
        conn.close()


def add_db_element(db_path, Structure_data, added_masses_data, Meta_infos):
    log.debug(Meta_infos.to_string())
    META = load_db_table(db_path, "META")

    Identifier = Meta_infos["Identifier"].values[0]
    if Identifier in META["Identifier"].values:
        _ = ex.show_message_box("GeometrieConverter.xlsm", "The provided Identifier of the new structure is already in the database, please provide a unique name")
        return False

    create_db_table(db_path, Identifier, Structure_data, if_exists='fail')
    create_db_table(db_path, f"{Identifier}__ADDED_MASSES", added_masses_data, if_exists='fail')

    META = pd.concat([META, Meta_infos], axis=0)
    create_db_table(db_path, "META", META, if_exists='replace')

    _ = ex.show_message_box("GeometrieConverter.xlsm", f"Data saved in new Database entry {Identifier}")

    return True


def delete_db_element(db_path, Identifier):
    META = load_db_table(db_path, "META")

    META.drop(META[META["Identifier"] == Identifier].index, inplace=True)

    drop_db_table(db_path, Identifier)
    drop_db_table(db_path, Identifier + "__ADDED_MASSES")

    create_db_table(db_path, "META", META, if_exists='replace')
    return


def replace_db_element(db_path, Structure_data, added_masses_data, Meta_infos, old_id):
    META = load_db_table(db_path, "META")
    new_id = Meta_infos["Identifier"].values[0]

    # replace data in meta
    META.loc[META["Identifier"] == old_id, :] = Meta_infos.iloc[0].values

    if META["Identifier"].value_counts().get(Meta_infos.iloc[0].values[0], 0) > 1:
        _ = ex.show_message_box("GeometrieConverter.xlsm", f"{new_id} is already taken in database, please choose a different name.")
        return False

    drop_db_table(db_path, old_id)

    sucess = write_db_element_data(db_path, new_id, Structure_data, added_masses_data)

    if not sucess:
        return False

    create_db_table(db_path, "META", META, if_exists="replace")

    _ = ex.show_message_box("GeometrieConverter.xlsm", f"Data in {old_id} overwriten (now named {new_id})")

    return True


def write_db_element_data(db_path, change_id, Structure_data, added_masses_data):
    if pd.isna(Structure_data.values).any():
        _ = ex.show_message_box("GeometrieConverter.xlsm", f"Structure data contains invalid values, please correct")
        return False

    # if pd.isna(added_masses_data.values).any():
    #     _ = ex.show_message_box("GeometrieConverter.xlsm", f"Added Masses data contains invalid values, please correct")
    #     return False

    create_db_table(db_path, change_id, Structure_data, if_exists="replace")
    create_db_table(db_path, change_id + "__ADDED_MASSES", added_masses_data, if_exists="replace")

    return True


def check_db_integrity():
    return


def load_META(Structure, db_path):
    """
    Load the META table from the  database and update the structures dropdown
    in the Excel workbook.

    Args:
        Structure (str): Name of the structure to load (MP, TP,...)
        db_path (str): Path to the MP SQLite database.

    Returns:
        None
    """
    logger = ex.setup_logger()
    sheet_name_structure_loading = "BuildYourStructure"

    META = load_db_table(db_path, "META")
    ex.set_dropdown_values(
        "GeometrieConverter.xlsm",
        sheet_name_structure_loading,
        f"Dropdown_{Structure}_Structures",
        list(META.loc[:, "Identifier"].values)
    )
    ex.write_df_to_table("GeometrieConverter.xlsm", sheet_name_structure_loading, f"{Structure}_META_FULL", META)
    return


def load_DATA(Structure, Structure_name, db_path):
    """
    Load metadata and structure-specific data from the database
    and write them to the Excel workbook.

    Args:
        Stucture (str): Name of the structure to load (MP, TP,...)
        Structure_name (str): Name of the structure (table) to load.
        db_path (str): Path to the MP SQLite database.

    Returns:
        None
    """
    logger = ex.setup_logger()
    sheet_name_structure_loading = "BuildYourStructure"

    META = load_db_table(db_path, "META")
    DATA = load_db_table(db_path, Structure_name)
    MASSES = load_db_table(db_path, Structure_name + "__ADDED_MASSES")

    META_relevant = META.loc[META["Identifier"] == Structure_name]

    ex.write_df_to_table("GeometrieConverter.xlsm", sheet_name_structure_loading, f"{Structure}_META_TRUE", META_relevant)
    ex.write_df_to_table("GeometrieConverter.xlsm", sheet_name_structure_loading, f"{Structure}_META", META_relevant)
    ex.write_df_to_table("GeometrieConverter.xlsm", sheet_name_structure_loading, f"{Structure}_DATA_TRUE", DATA)
    ex.write_df_to_table("GeometrieConverter.xlsm", sheet_name_structure_loading, f"{Structure}_DATA", DATA)
    ex.write_df_to_table("GeometrieConverter.xlsm", sheet_name_structure_loading, f"{Structure}_MASSES_TRUE", MASSES)
    ex.write_df_to_table("GeometrieConverter.xlsm", sheet_name_structure_loading, f"{Structure}_MASSES", MASSES)

    ex.clear_excel_table_contents("GeometrieConverter.xlsm", sheet_name_structure_loading, f"{Structure}_META_NEW")
    ex.call_vba_dropdown_macro("GeometrieConverter.xlsm", sheet_name_structure_loading, f"Dropdown_{Structure}_Structures", Structure_name)


def save_data(Structure, db_path, selected_structure):
    """
    Saves data from an Excel sheet and updates a database based on changes in structure metadata and data.

    This function loads the full metadata and data for a given structure, compares the current data with the existing data in the
    database, and handles the saving of new data or updating existing entries in the database. The function follows a series of checks
    to validate data, handle new entries, overwrite existing entries, and ensure data integrity.

    The function performs the following:
    1. Validates and processes the current data and metadata.
    2. Checks if new metadata is fully populated and whether it represents a new structure or an update.
    3. Saves the data to a new database table if the structure is new, or overwrites the existing structure if the metadata has changed.
    4. Displays message boxes to inform the user of the progress, errors, or status of the operation.

    Parameters:
    -----------
    Structure : str
        The name of the structure whose data and metadata need to be saved or updated.
    db_path : str
        The path to the database where the data and metadata will be saved.
    selected_structure : str
        The name of the structure that is selected for saving or updating.

    Returns:
    --------
    bool
        A boolean indicating whether the data was successfully saved or updated.
    str
        The name of the structure after the operation (could be a new name or the same).
    """
    def saving_logic(META_FULL, META_DB, META_CURR, META_CURR_NEW, DATA_DB, DATA_CURR, MASSES_DB, MASSES_CURR):

        def valid_data(data):
            if pd.isna(data.values).any():
                return False, data
            try:
                return True, data.astype(float)
            except (ValueError, TypeError):
                return False, data

        succes, DATA_CURR = valid_data(DATA_CURR)

        if not succes:
            _ = ex.show_message_box("GeometrieConverter.xlsm",
                                    "Invalid data found in Structure data! Aborting.")
            return False, _

        data_changed = not (DATA_DB.equals(DATA_CURR)) or not (MASSES_DB.equals(MASSES_CURR))
        meta_loaded_changed = not (META_DB.values[0][0:-1] == META_CURR.values[0][0:-1]).all()
        meta_new_populated = (META_CURR_NEW.values[0][0:-2] != 'None').any()

        if meta_new_populated:
            if not ((META_CURR_NEW.values[0][0:-2] != "None").all()):
                _ = ex.show_message_box("GeometrieConverter.xlsm",
                                        "Please fully populate the NEW Meta table to create a new DB entry or clear it of all data to overwrite the loaded Structure")
                return False, _

            sucess = add_db_element(db_path, DATA_CURR, MASSES_CURR, META_CURR_NEW)

            if sucess:
                return True, META_CURR_NEW["Identifier"].values[0]
            else:
                return False, None

        if meta_loaded_changed:
            if not ((META_CURR.values[0][0:-1] != None).all()):
                _ = ex.show_message_box("GeometrieConverter.xlsm", "Please fully populate the Current Meta table to modify the DB entry.")
                return False, _

            sucess = replace_db_element(db_path, DATA_CURR, MASSES_CURR, META_CURR, selected_structure)

            if sucess:
                return True, META_CURR["Identifier"].values[0]
            else:
                return False, None

        if data_changed:
            sucess = write_db_element_data(db_path, selected_structure, DATA_CURR, MASSES_CURR)

            if sucess:
                return True, META_CURR["Identifier"].values[0]
            else:
                return False, None

        _ = ex.show_message_box("GeometrieConverter.xlsm", f"No changes detected.")
        return False, _

    META_FULL = load_db_table(db_path, "META")
    META_CURR = ex.read_excel_table("GeometrieConverter.xlsm", "BuildYourStructure", f"{Structure}_META", dtype=str)
    META_CURR_NEW = ex.read_excel_table("GeometrieConverter.xlsm", "BuildYourStructure", f"{Structure}_META_NEW", dtype=str)
    DATA_CURR = ex.read_excel_table("GeometrieConverter.xlsm", "BuildYourStructure", f"{Structure}_DATA", dtype=float)
    MASSES_CURR = ex.read_excel_table("GeometrieConverter.xlsm", "BuildYourStructure", f"{Structure}_MASSES")

    DATA_CURR = DATA_CURR.dropna(how='all')
    MASSES_CURR = MASSES_CURR.dropna(how='all')

    if selected_structure != "":
        META_DB = META_FULL.loc[META_FULL["Identifier"] == selected_structure]
        DATA_DB = load_db_table(db_path, selected_structure, dtype=float)
        MASSES_DB = load_db_table(db_path, selected_structure + "__ADDED_MASSES")
        saved, structure_load_after = saving_logic(META_FULL, META_DB, META_CURR, META_CURR_NEW, DATA_DB, DATA_CURR, MASSES_DB, MASSES_CURR)

    else:
        if not ((META_CURR_NEW.values[0][0:-2] != "None").all()):
            _ = ex.show_message_box("GeometrieConverter.xlsm",
                                    "Please fully populate the NEW Meta table to create a new DB entry or clear it of all data to overwrite the loaded Structure")
            return
        else:
            saved = add_db_element(db_path, DATA_CURR, MASSES_CURR, META_CURR_NEW)
            structure_load_after = META_CURR_NEW["Identifier"].values[0]

    if saved:
        load_META(Structure, db_path)

        load_DATA(Structure, structure_load_after, db_path)


def delete_data(Structure, db_path, selected_structure):
    answer = ex.show_message_box("GeometrieConverter.xlsm", f"Are you sure you want to delete the structure {selected_structure} from the database?", icon="vbYesNo",
                                 buttons="vbYesNo")
    logger = ex.setup_logger()
    logger.debug(answer)
    if answer == "Yes":
        delete_db_element(db_path, selected_structure)

        load_META(Structure, db_path)

        ex.clear_excel_table_contents("GeometrieConverter.xlsm", "BuildYourStructure", f"{Structure}_META_NEW")
        ex.clear_excel_table_contents("GeometrieConverter.xlsm", "BuildYourStructure", f"{Structure}_META_TRUE")
        ex.clear_excel_table_contents("GeometrieConverter.xlsm", "BuildYourStructure", f"{Structure}_META")
        ex.clear_excel_table_contents("GeometrieConverter.xlsm", "BuildYourStructure", f"{Structure}_DATA_TRUE")
        ex.clear_excel_table_contents("GeometrieConverter.xlsm", "BuildYourStructure", f"{Structure}_DATA")
        ex.clear_excel_table_contents("GeometrieConverter.xlsm", "BuildYourStructure", f"{Structure}_MASSES_TRUE")
        ex.clear_excel_table_contents("GeometrieConverter.xlsm", "BuildYourStructure", f"{Structure}_MASSES")

    return


# %% MP
def load_MP_META(db_path):
    """
    Load the META table from the MP database and update the MP structures dropdown
    in the Excel workbook.

    Args:
        db_path (str): Path to the MP SQLite database.

    Returns:
        None
    """
    load_META("MP", db_path)


def load_MP_DATA(Structure_name, db_path):
    """
    Load metadata and structure-specific data from the MP database
    and write them to the Excel workbook.

    Args:
        Structure_name (str): Name of the structure (table) to load.
        db_path (str): Path to the MP SQLite database.

    Returns:
        None
    """

    load_DATA("MP", Structure_name, db_path)


def save_MP_data(db_path, selected_structure):
    save_data("MP", db_path, selected_structure)

    return


def delete_MP_data(db_path, selected_structure):
    delete_data("MP", db_path, selected_structure)

    return


def load_MP_from_MPTool(MP_path):
    try:
        Section_col = ex.read_excel_range(MP_path, "Geometry", "C1:C1000")
        Section_col = Section_col.iloc[:, 0].dropna()
        row_MP = Section_col[Section_col=="Section"].index.values[1]

        Data = ex.read_excel_range(MP_path, "Geometry", f"C{row_MP+3}:H1000", dtype=float)
        Data = Data.dropna(how="all")
        ex.write_df_to_table("GeometrieConverter.xlsm", "BuildYourStructure", "MP_DATA", Data)
    except Exception as e:
        ex.show_message_box("GeometrieConverter.xlsm",
                            f"Error reading {MP_path}. Please make shure, the path leads to a valid MP_tool xlsm file and has the MP data in the range C27:H1000, empty rows allowed. Error trown by Python: {e}")
        return
    return


def load_TP_from_MPTool(MP_path):
    try:
        Section_col = ex.read_excel_range(MP_path, "Geometry", "C1:C1000")
        Section_col = Section_col.iloc[:, 0].dropna()
        row_TP = Section_col[Section_col=="Section"].index.values[0]
        row_MP = Section_col[Section_col=="Section"].index.values[1]

        Data = ex.read_excel_range(MP_path, "Geometry", f"C{row_TP+3}:H{row_MP-2}", dtype=float)
        Data = Data.dropna(how="all")
        ex.write_df_to_table("GeometrieConverter.xlsm", "BuildYourStructure", "TP_DATA", Data)
    except Exception as e:
        ex.show_message_box("GeometrieConverter.xlsm",
                        f"Error reading {MP_path}. Please make shure, the path leads to a valid MP_tool xlsm file and has the TP data in the range C11:H23, empty rows allowed. Error trown by Python: {e}")
    return


# %% TP
def load_TP_META(db_path):
    """
    Load the META table from the MP database and update the MP structures dropdown
    in the Excel workbook.

    Args:
        db_path (str): Path to the TP SQLite database.

    Returns:
        None
    """
    load_META("TP", db_path)


def load_TP_DATA(Structure_name, db_path):
    """
    Load metadata and structure-specific data from the TP database
    and write them to the Excel workbook.

    Args:
        Structure_name (str): Name of the structure (table) to load.
        db_path (str): Path to the TP SQLite database.

    Returns:
        None
    """

    load_DATA("TP", Structure_name, db_path)


def save_TP_data(db_path, selected_structure):
    save_data("TP", db_path, selected_structure)

    return


def delete_TP_data(db_path, selected_structure):
    delete_data("TP", db_path, selected_structure)

    return


# %% TOWER
def load_TOWER_META(db_path):
    """
    Load the META table from the MP database and update the MP structures dropdown
    in the Excel workbook.

    Args:
        db_path (str): Path to the TOWER SQLite database.

    Returns:
        None
    """
    load_META("TOWER", db_path)


def load_TOWER_DATA(Structure_name, db_path):
    """
    Load metadata and structure-specific data from the TOWER database
    and write them to the Excel workbook.

    Args:
        Structure_name (str): Name of the structure (table) to load.
        db_path (str): Path to the TOWER SQLite database.

    Returns:
        None
    """

    load_DATA("TOWER", Structure_name, db_path)


def save_TOWER_data(db_path, selected_structure):
    save_data("TOWER", db_path, selected_structure)

    return


def delete_TOWER_data(db_path, selected_structure):
    delete_data("TOWER", db_path, selected_structure)

    return
