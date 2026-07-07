import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:webview_flutter/webview_flutter.dart';

import '../services/post_studio_bridge_handler.dart';
import '../state/app_state.dart';
import '../utils/app_strings.dart';

/// Full editor parity with desktop's Post Studio: mounts the same client-side
/// WYSIWYG editor bundle (static/post_studio/, synced into
/// assets/post_studio/) inside a WebView, bridged to ClinicApi via
/// [PostStudioBridgeHandler]. Replaces the old read-only PostsScreen.
class PostStudioScreen extends StatefulWidget {
  const PostStudioScreen({super.key});

  @override
  State<PostStudioScreen> createState() => _PostStudioScreenState();
}

class _PostStudioScreenState extends State<PostStudioScreen> {
  late final WebViewController _controller;
  bool _loadFailed = false;
  bool _initialized = false;
  bool _initialLoadComplete = false;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_initialized) return;
    _initialized = true;
    final handler = PostStudioBridgeHandler(
      api: context.read<AppState>().api,
      runJavaScript: (script) => _controller.runJavaScript(script),
    );
    _controller = WebViewController()
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..setNavigationDelegate(NavigationDelegate(
        onPageFinished: (_) => _initialLoadComplete = true,
        onNavigationRequest: _onNavigationRequest,
        onWebResourceError: (error) {
          if (error.isForMainFrame != false && mounted) {
            setState(() => _loadFailed = true);
          }
        },
      ))
      ..addJavaScriptChannel(
        'PostStudioBridge',
        onMessageReceived: (message) => unawaited(handler.onMessage(message.message)),
      )
      ..loadFlutterAsset('assets/post_studio/mobile_editor.html');
  }

  // Never load arbitrary URLs. The bundled editor is a closed SPA that never
  // navigates after its own initial load (no links, no window.open, no
  // location changes) — so only navigations observed before that first load
  // finishes can possibly be part of it; anything after is never legitimate,
  // on every platform, regardless of whether onNavigationRequest happens to
  // fire for the initial load itself.
  NavigationDecision _onNavigationRequest(NavigationRequest request) {
    if (_initialLoadComplete) return NavigationDecision.prevent;
    return NavigationDecision.navigate;
  }

  @override
  Widget build(BuildContext context) {
    final ar = context.watch<AppState>().isArabic;
    if (_loadFailed) {
      return Scaffold(
        body: Center(child: Text(AppStrings.t('failed_to_load_data', isArabic: ar))),
      );
    }
    return Scaffold(body: WebViewWidget(controller: _controller));
  }
}
