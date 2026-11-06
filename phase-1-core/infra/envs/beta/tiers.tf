# The three server tiers: edge, backend and data.
resource "aws_subnet" "private_backend" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "10.20.1.0/24"
  availability_zone       = "${var.region}a"
  map_public_ip_on_launch = false

  tags = { Name = "${local.name_prefix}-private-backend" }
}

resource "aws_subnet" "private_data" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "10.20.2.0/24"
  availability_zone       = "${var.region}a"
  map_public_ip_on_launch = false

  tags = { Name = "${local.name_prefix}-private-data" }
}

resource "aws_eip" "nat" {
  domain = "vpc"
  tags   = { Name = "${local.name_prefix}-nat-ip" }
}

resource "aws_nat_gateway" "main" {
  allocation_id = aws_eip.nat.id
  subnet_id     = aws_subnet.public_a.id
  tags          = { Name = "${local.name_prefix}-nat" }

  depends_on = [aws_internet_gateway.main]
}

resource "aws_route_table" "private" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.main.id
  }

  tags = { Name = "${local.name_prefix}-private-rt" }
}

resource "aws_route_table_association" "private_backend" {
  subnet_id      = aws_subnet.private_backend.id
  route_table_id = aws_route_table.private.id
}

resource "aws_route_table_association" "private_data" {
  subnet_id      = aws_subnet.private_data.id
  route_table_id = aws_route_table.private.id
}

resource "aws_vpc_endpoint" "s3" {
  vpc_id            = aws_vpc.main.id
  service_name      = "com.amazonaws.${var.region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [aws_route_table.private.id, aws_route_table.public.id]
  tags              = { Name = "${local.name_prefix}-s3-endpoint" }
}

resource "aws_security_group" "edge" {
  name        = "${local.name_prefix}-edge-sg"
  description = "Edge node: HTTPS and HTTP from the internet; cluster traffic from other tiers"
  vpc_id      = aws_vpc.main.id
  tags        = { Name = "${local.name_prefix}-edge-sg" }
}

resource "aws_security_group" "backend" {
  name        = "${local.name_prefix}-backend-sg"
  description = "Backend node: cluster traffic from other tiers only; no internet inbound"
  vpc_id      = aws_vpc.main.id
  tags        = { Name = "${local.name_prefix}-backend-sg" }
}

resource "aws_security_group" "data" {
  name        = "${local.name_prefix}-data-sg"
  description = "Data node: cluster traffic from other tiers only; no internet inbound"
  vpc_id      = aws_vpc.main.id
  tags        = { Name = "${local.name_prefix}-data-sg" }
}

locals {
  tier_sgs = {
    edge    = aws_security_group.edge.id
    backend = aws_security_group.backend.id
    data    = aws_security_group.data.id
  }
  tier_pairs = {
    for pair in setproduct(keys(local.tier_sgs), keys(local.tier_sgs)) :
    "${pair[0]}-from-${pair[1]}" => { to = pair[0], from = pair[1] } if pair[0] != pair[1]
  }
}

resource "aws_vpc_security_group_ingress_rule" "wireguard" {
  for_each                     = local.tier_pairs
  security_group_id            = local.tier_sgs[each.value.to]
  referenced_security_group_id = local.tier_sgs[each.value.from]
  description                  = "Encrypted pod network (flannel WireGuard)"
  ip_protocol                  = "udp"
  from_port                    = 51820
  to_port                      = 51820
}

resource "aws_vpc_security_group_ingress_rule" "kubelet" {
  for_each                     = local.tier_pairs
  security_group_id            = local.tier_sgs[each.value.to]
  referenced_security_group_id = local.tier_sgs[each.value.from]
  description                  = "kubelet (logs, exec, metrics)"
  ip_protocol                  = "tcp"
  from_port                    = 10250
  to_port                      = 10250
}

resource "aws_vpc_security_group_ingress_rule" "k3s_api" {
  for_each                     = toset(["edge", "backend"])
  security_group_id            = aws_security_group.data.id
  referenced_security_group_id = local.tier_sgs[each.key]
  description                  = "k3s API (agents join and report to the server)"
  ip_protocol                  = "tcp"
  from_port                    = 6443
  to_port                      = 6443
}

resource "aws_vpc_security_group_ingress_rule" "edge_https" {
  security_group_id = aws_security_group.edge.id
  description       = "HTTPS to Traefik"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  cidr_ipv4         = "0.0.0.0/0"
}

resource "aws_vpc_security_group_ingress_rule" "edge_http" {
  security_group_id = aws_security_group.edge.id
  description       = "HTTP to Traefik: certificate (ACME) checks and redirect to HTTPS only"
  ip_protocol       = "tcp"
  from_port         = 80
  to_port           = 80
  cidr_ipv4         = "0.0.0.0/0"
}

resource "aws_vpc_security_group_egress_rule" "all_out" {
  for_each          = local.tier_sgs
  security_group_id = each.value
  description       = "Outbound: images, AWS APIs, model providers, sign-in (via NAT if private)"
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"
}

resource "random_password" "k3s_token" {
  length  = 64
  special = false
}

resource "aws_secretsmanager_secret" "cluster" {
  name                    = "${var.project}/${var.environment}/cluster"
  description             = "k3s join token shared by the three nodes"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "cluster" {
  secret_id     = aws_secretsmanager_secret.cluster.id
  secret_string = jsonencode({ k3s_token = random_password.k3s_token.result })
}

data "aws_iam_policy_document" "read_cluster_secret" {
  statement {
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [aws_secretsmanager_secret.cluster.arn]
  }
}

resource "aws_iam_role_policy" "node_read_cluster_secret" {
  name   = "${local.name_prefix}-read-cluster-secret"
  role   = aws_iam_role.node.id
  policy = data.aws_iam_policy_document.read_cluster_secret.json
}

resource "aws_iam_role" "agent" {
  name               = "${local.name_prefix}-agent-role"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume_role.json
}

resource "aws_iam_role_policy_attachment" "agent_ssm" {
  role       = aws_iam_role.agent.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_role_policy" "agent_pull_images" {
  name   = "${local.name_prefix}-agent-pull-images"
  role   = aws_iam_role.agent.id
  policy = data.aws_iam_policy_document.pull_images.json
}

resource "aws_iam_role_policy" "agent_read_cluster_secret" {
  name   = "${local.name_prefix}-agent-read-cluster-secret"
  role   = aws_iam_role.agent.id
  policy = data.aws_iam_policy_document.read_cluster_secret.json
}

resource "aws_iam_instance_profile" "agent" {
  name = "${local.name_prefix}-agent-profile"
  role = aws_iam_role.agent.name
}

locals {
  node_common = {
    ami           = data.aws_ssm_parameter.al2023_arm64.insecure_value
    instance_type = var.data_node_instance_type
  }
}

resource "aws_instance" "data" {
  ami                         = local.node_common.ami
  instance_type               = local.node_common.instance_type
  subnet_id                   = aws_subnet.private_data.id
  vpc_security_group_ids      = [aws_security_group.data.id]
  iam_instance_profile        = aws_iam_instance_profile.node.name
  associate_public_ip_address = false
  user_data_replace_on_change = true

  user_data = templatefile("${path.module}/templates/data-server.sh.tftpl", {
    region              = var.region
    secret_id           = aws_secretsmanager_secret.database.name
    cluster_secret_id   = aws_secretsmanager_secret.cluster.name
    k3s_version         = var.k3s_version
    ecr_cp_version      = var.ecr_credential_provider_version
    ecr_cp_sha256       = var.ecr_credential_provider_sha256
    postgres_image      = var.postgres_image
    redis_image         = var.redis_image
    database_name       = local.database_name
    database_admin_user = local.database_admin_user
    database_owner_user = local.database_owner_user
    database_app_user   = local.database_app_user
    redis_app_user      = local.redis_app_user
    redis_admin_user    = local.redis_admin_user
    postgres_cluster_ip = local.postgres_cluster_ip
    redis_cluster_ip    = local.redis_cluster_ip
  })

  metadata_options {
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
  }

  root_block_device {
    volume_size = 20
    volume_type = "gp3"
    encrypted   = true
  }

  lifecycle {
    ignore_changes = [ami]
  }

  depends_on = [
    aws_secretsmanager_secret_version.database,
    aws_secretsmanager_secret_version.cluster,
    aws_route_table_association.private_data,
    aws_nat_gateway.main,
  ]

  tags = { Name = "${local.name_prefix}-data-01", Tier = "data" }
}

resource "aws_instance" "agent" {
  for_each = {
    edge = {
      subnet     = aws_subnet.public_a.id
      sg         = aws_security_group.edge.id
      public     = true
      extra_args = " --node-label svccontroller.k3s.cattle.io/enablelb=true"
    }
    backend = {
      subnet     = aws_subnet.private_backend.id
      sg         = aws_security_group.backend.id
      public     = false
      extra_args = ""
    }
  }

  ami                         = local.node_common.ami
  instance_type               = local.node_common.instance_type
  subnet_id                   = each.value.subnet
  vpc_security_group_ids      = [each.value.sg]
  iam_instance_profile        = aws_iam_instance_profile.agent.name
  associate_public_ip_address = each.value.public
  user_data_replace_on_change = true

  user_data = templatefile("${path.module}/templates/agent-node.sh.tftpl", {
    region            = var.region
    cluster_secret_id = aws_secretsmanager_secret.cluster.name
    k3s_version       = var.k3s_version
    ecr_cp_version    = var.ecr_credential_provider_version
    ecr_cp_sha256     = var.ecr_credential_provider_sha256
    server_ip         = aws_instance.data.private_ip
    tier              = each.key
    extra_args        = each.value.extra_args
  })

  metadata_options {
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
  }

  root_block_device {
    volume_size = 20
    volume_type = "gp3"
    encrypted   = true
  }

  lifecycle {
    ignore_changes = [ami]
  }

  depends_on = [
    aws_secretsmanager_secret_version.cluster,
    aws_route_table_association.private_backend,
    aws_nat_gateway.main,
  ]

  tags = { Name = "${local.name_prefix}-${each.key}-01", Tier = each.key }
}
