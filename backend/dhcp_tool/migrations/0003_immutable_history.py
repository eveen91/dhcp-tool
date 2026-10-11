from django.db import migrations

SQL = """
CREATE FUNCTION dhcp_tool_immutable_history() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'Published history is immutable' USING ERRCODE = '23514';
END;
$$;
CREATE TRIGGER immutable_version BEFORE UPDATE OR DELETE ON dhcp_tool_version
FOR EACH ROW EXECUTE FUNCTION dhcp_tool_immutable_history();
CREATE TRIGGER immutable_artifact BEFORE UPDATE OR DELETE ON dhcp_tool_artifact
FOR EACH ROW EXECUTE FUNCTION dhcp_tool_immutable_history();
"""
REVERSE = """
DROP TRIGGER immutable_artifact ON dhcp_tool_artifact;
DROP TRIGGER immutable_version ON dhcp_tool_version;
DROP FUNCTION dhcp_tool_immutable_history();
"""


class Migration(migrations.Migration):
    dependencies = [("dhcp_tool", "0002_version_firewall_description_firewall_location_and_more")]
    operations = [migrations.RunSQL(SQL, REVERSE)]
