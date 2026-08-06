import re

def extract_json(filepath, prefix):
    with open(filepath, "r") as f:
        for line in f:
            if prefix in line:
                # Extract the json part
                part = line.split(prefix, 1)[1].strip()
                return part
    return None

def main():
    client_json = extract_json("/tmp/client_out.txt", "CLIENT SIGNABLE BYTES:")
    oracle_json = extract_json("/tmp/oracle_logs.txt", "ORACLE SIGNABLE BYTES:")

    if not client_json:
        print("Could not find client json in /tmp/client_out.txt")
        return
    if not oracle_json:
        print("Could not find oracle json in /tmp/oracle_logs.txt")
        return

    print(f"Client length: {len(client_json)}")
    print(f"Oracle length: {len(oracle_json)}")

    if client_json == oracle_json:
        print("The strings are EXACTLY identical!")
        return

    # Find first diff
    min_len = min(len(client_json), len(oracle_json))
    for i in range(min_len):
        if client_json[i] != oracle_json[i]:
            print(f"Diff found at index {i}:")
            print(f"Client: {client_json[i-20:i+20]!r}")
            print(f"Oracle: {oracle_json[i-20:i+20]!r}")
            break
    else:
        print("No diff found up to min length, one is a prefix of another")

if __name__ == "__main__":
    main()
