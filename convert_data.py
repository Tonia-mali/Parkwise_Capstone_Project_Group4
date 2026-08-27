import pandas as pd
import json

# 1. Load the master dataset
df = pd.read_csv('nairobi_parking_master_dataset.csv')

# 2. Keep only the columns the frontend needs
columns_to_keep = [
    'facility_name_clean', 'latitude', 'longitude', 
    'base_rate_kes', 'traffic_delay_index', 'calibration_status',
    'overall_rating', 'operating_hours', 'capacity' 
]

df_subset = df[columns_to_keep].copy()

# 3. Fill missing values (NaNs) with a safe default so the map doesn't crash
df_subset['base_rate_kes'] = df_subset['base_rate_kes'].fillna("Unknown")
df_subset['traffic_delay_index'] = df_subset['traffic_delay_index'].fillna(1.0)

# 4. Convert to a JavaScript file that your HTML can load directly
json_data = df_subset.to_dict(orient='records')
with open('facilities.js', 'w') as f:
    f.write(f"const parkingData = {json.dumps(json_data, indent=2)};")

print("facilities.js created successfully!")