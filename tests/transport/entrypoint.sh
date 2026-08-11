#!/bin/sh
set -eu

fixture_dir=/fixtures
git_root=/srv/git
http_user=$(cat "$fixture_dir/http_username")
http_password=$(cat "$fixture_dir/http_password")

mkdir -p "$git_root" /run/sshd /home/git/.ssh

if ! id git >/dev/null 2>&1; then
    useradd --create-home --home-dir /home/git --shell /usr/bin/git-shell git
fi

cat "$fixture_dir/client.pub" "$fixture_dir/setup.pub" > /home/git/.ssh/authorized_keys
chmod 0700 /home/git/.ssh
chmod 0600 /home/git/.ssh/authorized_keys
chown -R git:git /home/git/.ssh

openssl req -x509 -newkey rsa:3072 -nodes -days 2 \
    -keyout "$fixture_dir/ca.key" \
    -out "$fixture_dir/ca.crt" \
    -subj "/CN=Redot Git Fixture CA" >/dev/null 2>&1
openssl req -newkey rsa:3072 -nodes \
    -keyout "$fixture_dir/server.key" \
    -out "$fixture_dir/server.csr" \
    -subj "/CN=localhost" >/dev/null 2>&1
cat > "$fixture_dir/server.ext" <<'EOF'
subjectAltName=DNS:localhost,IP:127.0.0.1
extendedKeyUsage=serverAuth
EOF
openssl x509 -req -days 2 \
    -in "$fixture_dir/server.csr" \
    -CA "$fixture_dir/ca.crt" \
    -CAkey "$fixture_dir/ca.key" \
    -CAcreateserial \
    -out "$fixture_dir/server.crt" \
    -extfile "$fixture_dir/server.ext" >/dev/null 2>&1

htpasswd -bc /etc/apache2/git.htpasswd "$http_user" "$http_password" >/dev/null
ssh-keygen -A >/dev/null 2>&1

for repository in https ssh; do
    git init --bare --initial-branch=main "$git_root/$repository.git" >/dev/null
done
git --git-dir="$git_root/https.git" config http.receivepack true

seed_dir=$(mktemp -d)
git -C "$seed_dir" init --initial-branch=main >/dev/null
git -C "$seed_dir" config user.name "Transport Fixture"
git -C "$seed_dir" config user.email "transport@example.invalid"
printf 'transport base\n' > "$seed_dir/base.txt"
git -C "$seed_dir" add base.txt
git -C "$seed_dir" commit -m "Transport base" >/dev/null
git -C "$seed_dir" remote add https "$git_root/https.git"
git -C "$seed_dir" remote add ssh "$git_root/ssh.git"
git -C "$seed_dir" push https main >/dev/null
git -C "$seed_dir" push ssh main >/dev/null
rm -rf "$seed_dir"

chown -R www-data:www-data "$git_root/https.git"
chown -R git:git "$git_root/ssh.git"

/usr/sbin/sshd
touch "$fixture_dir/ready"
exec apachectl -D FOREGROUND
