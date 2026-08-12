# Caddyfile templates

By default labops renders your Caddyfile from a built-in Jinja template. Point
`settings.proxy.template` at your own to change that — most often by *extending*
the built-in one and overriding a block or two.

The reference below is the same file that ships inside the package, next to the
template it documents.

{%
   include-markdown "../../ansible/files/proxy/README.md"
   heading-offset=1
%}
