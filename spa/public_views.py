from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import render
from django.urls import reverse
from xml.sax.saxutils import escape

def privacy(request):
    return render(request,"spa/policy.html",{"title":"Privacy Policy","privacy":True})

def cancellation_policy(request):
    return render(request,"spa/policy.html",{"title":"Cancellation & Rescheduling Policy"})

def sitemap_xml(request):
    routes = ["home","about","services","gallery","booking","contact","franchise","connect","privacy","cancellation_policy"]
    entries = "".join(f"<url><loc>{escape(settings.PUBLIC_SITE_URL + reverse(name))}</loc></url>" for name in routes)
    return HttpResponse('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'+entries+"</urlset>",content_type="application/xml")

def robots(request):
    return HttpResponse(f"User-agent: *\nDisallow: /admin/\nDisallow: /my-bookings/\nDisallow: /booking/success/\nDisallow: /verify-email/\nDisallow: /reset/\nSitemap: {settings.PUBLIC_SITE_URL}/sitemap.xml\n",content_type="text/plain")
