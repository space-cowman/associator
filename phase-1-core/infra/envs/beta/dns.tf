# The domain's DNS zone, public IP and inbound web traffic.
resource "aws_route53_zone" "public" {
  name          = var.domain
  comment       = "${local.name_prefix} public zone"
  force_destroy = true
}

resource "aws_eip" "node" {
  domain   = "vpc"
  instance = aws_instance.agent["edge"].id

  tags = { Name = "${local.name_prefix}-node-ip" }
}

resource "aws_route53_record" "apex" {
  zone_id = aws_route53_zone.public.zone_id
  name    = var.domain
  type    = "A"
  ttl     = 300
  records = [aws_eip.node.public_ip]
}

resource "aws_route53_record" "www" {
  zone_id = aws_route53_zone.public.zone_id
  name    = "www.${var.domain}"
  type    = "A"
  ttl     = 300
  records = [aws_eip.node.public_ip]
}

resource "aws_route53_record" "caa" {
  zone_id = aws_route53_zone.public.zone_id
  name    = var.domain
  type    = "CAA"
  ttl     = 3600
  records = ["0 issue \"letsencrypt.org\"", "0 issuewild \";\""]
}
