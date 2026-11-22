import pyodbc
import pandas as pd
from sqlalchemy import event

# 1. Opt into fast_executemany on this local engine (prevents HY090 via setinputsizes below)
engine = self._create_engine(
    self.database,
    self.server,
    self.secrets,
    fast_executemany=True,
)

# 2. Clean nulls and pre-calculate ODBC buffer sizes so row-to-row nulls never re-prepare or truncate
df_clean = dataframe.copy()
input_sizes = []

for col in df_clean.columns:
    s = df_clean[col]
    if pd.api.types.is_datetime64_any_dtype(s):
        # Guaranteed non-null filename date stays native datetime64
        input_sizes.append(None)
    elif pd.api.types.is_numeric_dtype(s):
        if s.isna().any():
            df_clean[col] = s.astype(object).where(s.notna(), None)
        input_sizes.append(None)
    else:
        # Convert NaN and empty strings "" to None so pyodbc never sees a 0-length buffer
        s_obj = s.astype(object)
        s_obj = s_obj.where(s_obj.notna() & (s_obj != ""), None)
        df_clean[col] = s_obj

        non_null = s_obj.dropna()
        max_len = int(non_null.astype(str).str.len().max()) if len(non_null) else 1
        input_sizes.append(
            (pyodbc.SQL_WLONGVARCHAR, 0, 0) if max_len > 4000 else (pyodbc.SQL_WVARCHAR, max(max_len, 1), 0)
        )

@event.listens_for(engine, "before_cursor_execute")
def lock_input_sizes(conn, cursor, statement, parameters, context, executemany):
    if executemany:
        cursor.setinputsizes(input_sizes)

# 3. Load in chunks using fast_executemany
df_clean.to_sql(
    table_name,
    engine,
    if_exists=if_exists,
    index=False,
    chunksize=50_000,
)
