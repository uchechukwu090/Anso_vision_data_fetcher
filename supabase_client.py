from supabase import create_client

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def get_watchlist_symbols():
    response = supabase.table("watchlist").select("symbol").execute()
    return [item["symbol"] for item in response.data]
